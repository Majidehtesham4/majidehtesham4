import json
import time

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..services import redact, registry

KINDS = [("action", "Action to Approve"), ("suggestion", "Suggestion"), ("info", "Request for Information")]
STATES = [
	("pending", "Waiting"),
	("approved", "Approved"),
	("executed", "Approved and Done"),
	("failed", "Approved, Failed"),
	("rejected", "Rejected"),
	("answered", "Answered"),
	("applied", "Applied by Hand"),
	("cancelled", "Cancelled"),
]


class AiApproval(models.Model):
	"""A person's decision an agent waits for. Only a person decides; an agent cannot approve, not even its
	own work, and the action then runs with the rights of the person who approved it."""

	_name = "veron.ai.approval"
	_description = "Agent Approval"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "state, id desc"

	name = fields.Char(readonly=True, default="/", copy=False)
	kind = fields.Selection(KINDS, required=True, readonly=True)
	state = fields.Selection(STATES, default="pending", required=True, readonly=True, tracking=True, index=True)
	run_id = fields.Many2one("veron.ai.run", readonly=True, index=True, ondelete="cascade")
	step_id = fields.Many2one("veron.ai.run.step", readonly=True, ondelete="set null")
	agent_id = fields.Many2one("veron.ai.agent", required=True, readonly=True, index=True, ondelete="cascade")
	company_id = fields.Many2one("res.company", readonly=True, index=True)
	tool_id = fields.Many2one("veron.ai.tool", readonly=True, ondelete="set null")
	tool_code = fields.Char(readonly=True)
	sensitive = fields.Selection(related="tool_id.sensitive")
	summary = fields.Text(readonly=True)
	reason = fields.Char("Why It Waits", readonly=True)
	payload_json = fields.Text("Arguments", readonly=True)
	amount = fields.Float(readonly=True)
	res_model = fields.Char(readonly=True)
	res_id = fields.Integer(readonly=True)
	approver_user_ids = fields.Many2many("res.users", string="Decided By Any Of", readonly=True)
	question = fields.Text(readonly=True)
	answer = fields.Text()
	decided_by = fields.Many2one("res.users", readonly=True)
	decided_at = fields.Datetime(readonly=True)
	decision_note = fields.Char("Note")
	result_json = fields.Text("Result", readonly=True)
	can_decide = fields.Boolean(compute="_compute_can_decide")

	def _compute_can_decide(self):
		for approval in self:
			approval.can_decide = approval.state == "pending" and approval._may_decide(self.env.user)

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", "/") == "/":
				vals["name"] = self.env["ir.sequence"].sudo().next_by_code("veron.ai.approval") or "/"
		return super().create(vals_list)

	# --- requested by a run

	@api.model
	def _request(self, run, step, tool, args, plan, decision, grant):
		approvers = grant._approvers() if grant else (run.agent_id.responsible_user_id | run.agent_id.supervisor_user_id)
		approval = self.create({
			"kind": "action" if decision == "approval" else "suggestion",
			"run_id": run.id, "step_id": step.id, "agent_id": run.agent_id.id, "company_id": run.company_id.id,
			"tool_id": step.tool_id.id, "tool_code": tool.code, "summary": plan.summary, "amount": plan.amount,
			"payload_json": json.dumps(args, ensure_ascii=False), "res_model": plan.model or False,
			"res_id": plan.res_ids[0] if plan.res_ids else False,
			"approver_user_ids": [(6, 0, approvers.ids)],
		})
		approval._remind()
		self.env["veron.ai.audit"]._log("approval_requested", agent=run.agent_id, run=run, tool=tool.code,
			description=plan.summary)
		return approval

	@api.model
	def _request_info(self, run, question):
		agent = run.agent_id
		approval = self.create({
			"kind": "info", "run_id": run.id, "agent_id": agent.id, "company_id": run.company_id.id,
			"summary": question[:500], "question": question,
			"approver_user_ids": [(6, 0, (agent.responsible_user_id | agent.supervisor_user_id).ids)],
		})
		approval._remind()
		return approval

	def _remind(self):
		for approval in self:
			for user in approval.approver_user_ids:
				approval.activity_schedule("mail.mail_activity_data_todo", user_id=user.id,
					summary=_("%(agent)s: %(kind)s", agent=approval.agent_id.name, kind=dict(KINDS)[approval.kind]),
					note=approval.summary)

	# --- decided by a person

	def _may_decide(self, user):
		self.ensure_one()
		if self.env.context.get("veron_ai_run_id") or user.veron_ai_service_user or user._is_public():
			return False
		if user in self.approver_user_ids or user.has_group("veron_ai_agent.group_ai_manager"):
			return True
		# The person who asked, for a tool that allows it; never a sensitive action
		grant = self.agent_id.sudo()._grant(self.tool_code) if self.tool_code else None
		return bool(grant and grant.requester_may_approve and not grant.tool_id.sensitive and self.run_id
			and self.run_id.sudo().initiator_user_id == user)

	def _check_decider(self):
		for approval in self:
			if approval.state != "pending":
				raise UserError(_("%s is already decided.", approval.name))
			if not approval._may_decide(self.env.user):
				raise AccessError(_("You do not decide %s. A person named on it, or an AI agents manager, does.",
					approval.name))

	def action_approve(self):
		"""The person approves: the action is checked again and done with that person's own rights"""
		self._check_decider()
		for approval in self:
			if approval.kind != "action":
				raise UserError(_("Only an action is approved; answer a question, or mark a suggestion as applied."))
			approval.write({"decided_by": self.env.uid, "decided_at": fields.Datetime.now(), "state": "approved"})
			self.env["veron.ai.audit"]._log("approval_approved", agent=approval.agent_id, run=approval.run_id,
				tool=approval.tool_code, description=approval.summary)
			approval._execute()
		return True

	def _execute(self):
		self.ensure_one()
		tool = registry.get(self.tool_code)
		# The agent's settings are read as configuration; the action itself runs with the approver's rights
		agent = self.agent_id.sudo()
		run = self.run_id
		grant = agent._grant(self.tool_code)
		if not tool or not grant:
			self.write({"state": "failed", "result_json": json.dumps({"error": "The tool is no longer granted."})})
			return
		env = agent._run_env(self.env.user)
		env = env(context=dict(env.context, veron_ai_run_id=run.id, veron_ai_approval_id=self.id))
		from .ai_run import ToolContext

		ctx = ToolContext(env, agent, run, grant)
		started = time.monotonic()
		step = self.env["veron.ai.run.step"].sudo().create({"run_id": run.id, "tool_code": tool.code, "origin": "approval",
			"tool_id": self.tool_id.id, "args_json": redact.dumps(json.loads(self.payload_json or "{}"), 8000),
			"sequence": len(run.step_ids) + 1})
		try:
			args = tool.validate(json.loads(self.payload_json or "{}"))
			with self.env.cr.savepoint():
				plan = tool.plan(ctx, args)
				output = tool.execute(ctx, args, plan)
		except (registry.ToolDenied, registry.ToolNeedsInfo, UserError, AccessError, ValueError) as error:
			message = redact.text(error, 500)
			self.write({"state": "failed", "result_json": json.dumps({"error": message}, ensure_ascii=False)})
			step.write({"decision": "failed", "message": message})
			self.message_post(body=_("Approved, but it could not be done: %s", message))
		else:
			output = output if isinstance(output, dict) else {"result": output}
			self.write({"state": "executed", "result_json": redact.dumps(output, 20000)})
			step.write({"decision": "allowed", "output_json": redact.dumps(output, 20000), "message": _("After approval"),
				"duration_ms": int((time.monotonic() - started) * 1000)})
		self.env["veron.ai.audit"]._log("approval_executed" if self.state == "executed" else "approval_failed",
			agent=agent, run=run, tool=tool.code, description=self.summary)
		self.activity_ids.action_feedback(_("Decided"))
		run._after_decision()

	def action_reject(self):
		self._check_decider()
		for approval in self:
			approval.write({"decided_by": self.env.uid, "decided_at": fields.Datetime.now(), "state": "rejected"})
			self.env["veron.ai.audit"]._log("approval_rejected", agent=approval.agent_id, run=approval.run_id,
				tool=approval.tool_code, description=approval.decision_note or approval.summary)
			approval.activity_ids.action_feedback(_("Rejected"))
			approval.run_id._after_decision()
		return True

	def action_applied(self):
		"""A suggestion the person carried out by hand"""
		self._check_decider()
		for approval in self:
			if approval.kind != "suggestion":
				raise UserError(_("Only a suggestion is marked as applied."))
			approval.write({"decided_by": self.env.uid, "decided_at": fields.Datetime.now(), "state": "applied"})
			approval.activity_ids.action_feedback(_("Applied"))
			approval.run_id._after_decision()
		return True

	def action_answer(self):
		self._check_decider()
		for approval in self:
			if approval.kind != "info":
				raise UserError(_("Only a question is answered."))
			if not approval.answer:
				raise UserError(_("Write the answer first."))
			approval.write({"decided_by": self.env.uid, "decided_at": fields.Datetime.now(), "state": "answered"})
			self.env["veron.ai.audit"]._log("info_answered", agent=approval.agent_id, run=approval.run_id,
				description=approval.question)
			approval.activity_ids.action_feedback(_("Answered"))
			approval.run_id._after_decision(answer=approval)
		return True

	def action_open_record(self):
		self.ensure_one()
		if not self.res_model or not self.res_id:
			raise UserError(_("This request has no record."))
		return {"type": "ir.actions.act_window", "res_model": self.res_model, "res_id": self.res_id, "view_mode": "form"}


class AiRunDecisions(models.Model):
	_inherit = "veron.ai.run"

	def _after_decision(self, answer=None):
		"""After a person's decision: the run is done when nothing waits; an answer starts a follow-up run"""
		for run in self.sudo():
			if not run or run.state not in ("waiting_info", "waiting_approval", "done_warning", "done"):
				continue
			pending = run.approval_ids.filtered(lambda a: a.state == "pending")
			if pending.filtered(lambda a: a.kind == "info"):
				run.state = "waiting_info"
			elif pending.filtered(lambda a: a.kind == "action"):
				run.state = "waiting_approval"
			elif run.state in ("waiting_info", "waiting_approval"):
				failed = run.approval_ids.filtered(lambda a: a.state in ("failed", "rejected"))
				run.write({"state": "done_warning" if failed or run.finding_ids.filtered(
					lambda f: f.severity != "info") else "done", "finished_at": fields.Datetime.now()})
				run.message_post(body=Markup("<p>%s</p>") % _("Every decision is made; the run is complete."))
			if answer and run.agent_id.enabled:
				follow = run._enqueue(run.agent_id, run.run_user_id, "retry", parent=run, sources=run.source_ids,
					conversation=run.conversation_id,
					text=f"{run.input_text or ''}\n\nAnswer of {answer.decided_by.name} to \"{answer.question}\":\n{answer.answer}")
				follow._execute()
