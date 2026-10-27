from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TASK_STATES = [("waiting", "Waiting for Other Tasks"), ("ready", "Ready"), ("running", "Running"), ("done", "Done"),
	("failed", "Failed"), ("cancelled", "Cancelled")]
REVIEWS = [("pending", "Not Reviewed"), ("accepted", "Accepted in the AI Review"), ("rejected", "Not Accepted"),
	("escalated", "Sent to a Person")]


class AiTask(models.Model):
	"""A piece of a supervisor's work, given to one of the agents it may delegate to. The supervisor reviews
	the result; its acceptance is an AI review, not an accounting or legal approval."""

	_name = "veron.ai.task"
	_description = "Agent Task"
	_order = "parent_run_id, sequence, id"

	name = fields.Char(required=True)
	sequence = fields.Integer(default=10)
	parent_run_id = fields.Many2one("veron.ai.run", "Supervisor Run", required=True, index=True, ondelete="cascade")
	supervisor_agent_id = fields.Many2one(related="parent_run_id.agent_id", store=True)
	agent_id = fields.Many2one("veron.ai.agent", "Given To", required=True)
	instructions = fields.Text()
	depends_on_ids = fields.Many2many("veron.ai.task", "veron_ai_task_depends_rel", "task_id", "depends_on_id",
		"After the Tasks")
	state = fields.Selection(TASK_STATES, default="ready", required=True, index=True)
	result_run_id = fields.Many2one("veron.ai.run", "Run of the Task", readonly=True)
	result_summary = fields.Html(related="result_run_id.output_html")
	review = fields.Selection(REVIEWS, default="pending", required=True)
	review_reason = fields.Text("Why")
	company_id = fields.Many2one(related="parent_run_id.company_id", store=True)

	@api.model
	def _delegate(self, run, agent, name, instructions, after=None):
		"""Called by the delegate tool; the supervisor may give tasks only to its own delegates"""
		supervisor = run.agent_id
		if not supervisor.is_supervisor:
			raise UserError(_("Only a supervisor agent gives tasks."))
		if agent not in supervisor.delegate_agent_ids:
			raise UserError(_("%(supervisor)s may not give tasks to %(agent)s.", supervisor=supervisor.name, agent=agent.name))
		if not agent.enabled:
			raise UserError(_("%s is not working.", agent.name))
		after = after or self.browse()
		task = self.sudo().create({
			"name": name, "parent_run_id": run.id, "agent_id": agent.id, "instructions": instructions,
			"depends_on_ids": [(6, 0, after.ids)], "state": "waiting" if after.filtered(lambda t: t.state != "done") else "ready",
			"sequence": len(run.sudo().child_run_ids) + 10,
		})
		return task

	def _start(self):
		"""A ready task runs with the rights of the supervisor run's user, never more"""
		for task in self.filtered(lambda t: t.state == "ready"):
			parent = task.parent_run_id
			depth, run = 0, parent
			while run.parent_run_id and depth < 5:
				depth, run = depth + 1, run.parent_run_id
			if depth >= 3:
				task.write({"state": "failed", "review_reason": _("Tasks are nested too deep.")})
				continue
			task.state = "running"
			run = self.env["veron.ai.run"].sudo()._enqueue(task.agent_id, parent.run_user_id, "supervisor",
				text=task.instructions, parent=parent, task=task, sources=parent.source_ids)
			task.result_run_id = run
			run._execute()

	def _on_run_done(self, run):
		for task in self:
			task.state = "done" if run.state in ("done", "done_warning", "waiting_approval", "waiting_info") else "failed"
			waiting = self.search([("parent_run_id", "=", task.parent_run_id.id), ("state", "=", "waiting")])
			ready = waiting.filtered(lambda t: all(d.state == "done" for d in t.depends_on_ids))
			ready.write({"state": "ready"})
			ready._start()
			if task.state == "failed":
				failed_after = waiting.filtered(lambda t: task in t.depends_on_ids)
				failed_after.write({"state": "cancelled", "review_reason": _("A task it depends on failed.")})

	def _review(self, decision, reason):
		for task in self:
			if task.state not in ("done", "failed"):
				raise UserError(_("A task is reviewed after it runs."))
			task.write({"review": decision, "review_reason": reason})
			if decision == "escalated":
				parent = task.parent_run_id
				user = parent.agent_id.supervisor_user_id or parent.agent_id.responsible_user_id
				parent.activity_schedule("mail.mail_activity_data_todo", user_id=user.id,
					summary=_("Review needed: %s", task.name), note=Markup("<p>%s</p>") % reason)

	def action_open_run(self):
		self.ensure_one()
		if not self.result_run_id:
			raise UserError(_("The task has not run yet."))
		return self.result_run_id._open()
