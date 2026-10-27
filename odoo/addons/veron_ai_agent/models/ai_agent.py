from datetime import datetime, timedelta

import pytz
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

from ..services import registry
from .ai_template import explain_tools

WEEKDAYS = [("0", "Monday"), ("1", "Tuesday"), ("2", "Wednesday"), ("3", "Thursday"), ("4", "Friday"), ("5", "Saturday"),
	("6", "Sunday")]
# Fields no agent reads, whatever the scope
SECRET_FIELD_WORDS = ("password", "token", "secret", "api_key", "signup", "totp", "oauth", "private_key")


def in_run(env):
	"""Raised when an agent run tries to change what only a person may change"""
	return AccessError(env._("An agent cannot change agents, their access or their authority; only a manager can."))


class AiAgent(models.Model):
	_name = "veron.ai.agent"
	_description = "AI Agent"
	_inherit = ["mail.thread"]
	_order = "sequence, name"

	name = fields.Char(required=True, tracking=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	enabled = fields.Boolean("Working", tracking=True, help="Off: the agent does not run, by schedule or by hand")
	template_id = fields.Many2one("veron.ai.agent.template", "Role", ondelete="restrict")
	category = fields.Selection(related="template_id.category", store=True)
	goal = fields.Text()
	description = fields.Text()
	instructions = fields.Text("Working Instructions", help="Laws, rates and tax rules never go here; tools read them from Odoo")
	playbook = fields.Text("Steps (JSON)")
	company_ids = fields.Many2many("res.company", string="Companies", required=True,
		default=lambda self: self.env.company)
	company_id = fields.Many2one("res.company", "Main Company", required=True, default=lambda self: self.env.company)
	responsible_user_id = fields.Many2one("res.users", "Responsible", required=True, tracking=True,
		default=lambda self: self.env.user, domain=[("share", "=", False)])
	supervisor_user_id = fields.Many2one("res.users", "Supervising Person", tracking=True, domain=[("share", "=", False)])
	run_as_user_id = fields.Many2one("res.users", "Runs As", tracking=True, domain=[("share", "=", False)],
		help="The user whose access rights a scheduled or event run has; a chat runs with the rights of the person chatting")
	user_ids = fields.Many2many("res.users", "veron_ai_agent_user_rel", "agent_id", "user_id", "Who May Use It",
		domain=[("share", "=", False)], help="Besides the responsible and the supervising person")
	is_supervisor = fields.Boolean("Supervisor", tracking=True)
	supervisor_agent_id = fields.Many2one("veron.ai.agent", "Supervisor Agent", domain=[("is_supervisor", "=", True)])
	delegate_agent_ids = fields.Many2many("veron.ai.agent", "veron_ai_agent_delegate_rel", "supervisor_id", "agent_id",
		"May Delegate To", help="The agents this supervisor may give tasks to")
	authority_level = fields.Selection(registry.LEVEL_NAMES, "Authority", required=True, default="1", tracking=True)
	grant_ids = fields.One2many("veron.ai.agent.tool", "agent_id", "Tools")
	scope_ids = fields.One2many("veron.ai.agent.scope", "agent_id", "Data")
	max_amount = fields.Float("Highest Amount", help="No action of a larger amount is done or proposed for auto-execution")
	max_risk = fields.Selection(registry.RISKS, "Highest Risk", default="high")
	max_steps = fields.Integer("Most Tool Calls of a Run", default=12)
	calendar_id = fields.Many2one("resource.calendar", "Working Hours")
	tz = fields.Selection("_tz_selection", "Time Zone", default=lambda self: self.env.user.tz or "Asia/Tehran")
	trigger_manual = fields.Boolean("By Hand and Chat", default=True)
	engine = fields.Selection([("auto", "AI When Available, Otherwise Built-in"), ("ai", "AI"),
		("internal", "Built-in Assistant Only")], "Answers With", default="auto", required=True,
		help="The built-in assistant answers from its library without a language model; the AI uses the provider")
	voice_engine = fields.Selection([("auto", "As Chosen in the Chat"), ("builtin", "Built-in, on the Server (No AI)"),
		("ai", "AI Service, Else Built-in")], "Voice Messages Read By", default="auto", required=True,
		help="Built-in: Vosk turns the voice into text on the server and nothing leaves it. AI: the speech-to-text "
			"service connected (e.g. Groq Whisper), the built-in one when it fails. As chosen in the chat: built-in "
			"while the built-in assistant is chosen, the AI while the AI is.")
	all_users = fields.Boolean("Every Internal User May Use It",
		help="Each person works with their own access rights: they see and do only what they may themselves")
	trigger_schedule = fields.Boolean("On a Schedule")
	trigger_event = fields.Boolean("On Events")
	event_codes = fields.Char("Events", help="Codes of the events that start it, separated by commas")
	schedule_ids = fields.One2many("veron.ai.schedule", "agent_id", "Schedules")
	expected_output = fields.Text()
	report_format = fields.Selection([("html", "In Odoo"), ("pdf", "In Odoo and as PDF")], default="html", required=True)
	notify_user_ids = fields.Many2many("res.users", "veron_ai_agent_notify_rel", "agent_id", "user_id", "Report To",
		domain=[("share", "=", False)])
	notify_channel_id = fields.Many2one("discuss.channel", "Report to Channel")
	notify_email = fields.Boolean("Also by Email")
	max_retries = fields.Integer("Tries After an Error", default=2)
	retry_delay = fields.Integer("Minutes Between Tries", default=15)
	escalate_user_id = fields.Many2one("res.users", "On Failure, Tell", domain=[("share", "=", False)])
	llm_provider_id = fields.Many2one("veron.ai.provider", "Language Model", domain=[("kind", "=", "llm")])
	vision_provider_id = fields.Many2one("veron.ai.provider", "Reading Photos and PDFs", domain=[("kind", "=", "vision")])
	search_provider_id = fields.Many2one("veron.ai.provider", "Web Search", domain=[("kind", "=", "search")])
	image_provider_id = fields.Many2one("veron.ai.provider", "Image Generation", domain=[("kind", "=", "image")])
	run_ids = fields.One2many("veron.ai.run", "agent_id")
	run_count = fields.Integer(compute="_compute_counts")
	approval_count = fields.Integer(compute="_compute_counts")
	last_run_id = fields.Many2one("veron.ai.run", compute="_compute_counts")
	explanation = fields.Html(compute="_compute_explanation", sanitize=False)

	@api.model
	def _tz_selection(self):
		return [(tz, tz) for tz in pytz.common_timezones]

	def _compute_counts(self):
		for agent in self:
			runs = self.env["veron.ai.run"].search([("agent_id", "=", agent.id)], order="id desc")
			agent.run_count = len(runs)
			agent.last_run_id = runs[:1]
			agent.approval_count = self.env["veron.ai.approval"].search_count([("agent_id", "=", agent.id), ("state", "=", "pending")])

	@api.depends("grant_ids.level", "grant_ids.active", "authority_level")
	def _compute_explanation(self):
		for agent in self:
			grants = agent.grant_ids.filtered("active")
			agent.explanation = self._explain(grants.tool_id, int(agent.authority_level), grants)

	@api.model
	def _explain(self, tools, level, grants=None):
		body = explain_tools(self.env, tools, level)
		if grants:
			auto = grants.filtered(lambda g: g.level == "4" and g.auto_execute)
			if auto:
				body += Markup("<p><b>%s</b> %s</p>") % (_("Acts on its own, within limits:"),
					", ".join(auto.tool_id.mapped("name")))
		return body + Markup("<p class='text-muted'>%s</p>") % _(
			"Posting, payments, bank details, deleting, closing a period, legal reports, publishing and contacting "
			"people outside always wait for a person's approval, unless a manager sets an explicit rule.")

	@api.constrains("company_id", "company_ids")
	def _check_company(self):
		for agent in self:
			if agent.company_id not in agent.company_ids:
				raise ValidationError(_("The main company is one of the agent's companies."))

	@api.constrains("supervisor_agent_id", "delegate_agent_ids")
	def _check_supervision(self):
		for agent in self:
			if agent.supervisor_agent_id == agent or agent in agent.delegate_agent_ids:
				raise ValidationError(_("An agent does not supervise itself."))

	@api.model_create_multi
	def create(self, vals_list):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		agents = super().create(vals_list)
		for agent in agents:
			self.env["veron.ai.audit"]._log("agent_created", agent=agent, description=agent.name)
		return agents

	def write(self, vals):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		watched = {"authority_level", "enabled", "company_ids", "run_as_user_id", "max_amount", "is_supervisor",
			"delegate_agent_ids", "user_ids"}
		before = {agent.id: agent.authority_level for agent in self}
		res = super().write(vals)
		if watched & set(vals):
			for agent in self:
				self.env["veron.ai.audit"]._log("agent_changed", agent=agent,
					description=_("Changed: %s", ", ".join(sorted(watched & set(vals)))),
					data={"authority_before": before.get(agent.id), "authority_after": agent.authority_level})
		return res

	def unlink(self):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		return super().unlink()

	# --- who may use it

	def _may_use(self, user):
		self.ensure_one()
		if self.all_users and not user.share and user.active:
			return True
		return user in (self.responsible_user_id | self.supervisor_user_id | self.user_ids) or user.has_group(
			"veron_ai_agent.group_ai_manager")

	# --- the environment of a run

	def _run_env(self, user):
		"""The environment of a run: the user's own rights, limited to the agent's companies"""
		self.ensure_one()
		companies = self.company_ids & user.company_ids
		if not companies:
			raise UserError(_("%(user)s has none of the companies of %(agent)s.", user=user.name, agent=self.name))
		main = self.company_id if self.company_id in companies else companies[:1]
		return self.env(user=user.id, context=dict(self.env.context, allowed_company_ids=[main.id] + (companies - main).ids,
			veron_ai_agent_id=self.id), su=False)

	def _in_working_hours(self, when=None):
		self.ensure_one()
		if not self.calendar_id:
			return True
		when = when or fields.Datetime.now()
		start = pytz.utc.localize(when)
		intervals = self.calendar_id._work_intervals_batch(start, start + timedelta(minutes=1),
			tz=pytz.timezone(self.tz or "Asia/Tehran"))[False]
		return bool(list(intervals))

	# --- the gate

	def _grant(self, code):
		self.ensure_one()
		return self.grant_ids.filtered(lambda g: g.active and g.tool_id.code == code)[:1]

	def _scope(self, model_name):
		self.ensure_one()
		return self.scope_ids.filtered(lambda s: s.model_id.model == model_name)[:1]

	def _scope_domain(self, model_name, env):
		"""The domain the agent may see of a model, or AccessError when the model is not in its data"""
		scope = self._scope(model_name)
		if not scope:
			raise registry.ToolDenied(_("The agent has no access to %s.", model_name))
		return scope._domain(env)

	def _readable_fields(self, model_name, env, requested=None):
		"""Fields of a model the agent may read for this user: in its scope, readable by the user, never secrets"""
		scope = self._scope(model_name)
		if not scope:
			raise registry.ToolDenied(_("The agent has no access to %s.", model_name))
		model = env[model_name]
		allowed = set(scope.field_ids.mapped("name")) if scope.field_ids else None
		names = []
		for name, field in model._fields.items():
			if field.type == "binary" or any(word in name for word in SECRET_FIELD_WORDS):
				continue
			if allowed is not None and name not in allowed and name not in ("id", "display_name"):
				continue
			if not model._has_field_access(field, "read"):
				continue
			names.append(name)
		if requested:
			refused = [name for name in requested if name not in names]
			if refused:
				raise registry.ToolDenied(_("The agent may not read: %s", ", ".join(refused)))
			return requested
		return names

	def _decide(self, tool, plan, env):
		"""allowed, approval, suggestion or denied, with the reason; nothing is done here"""
		self.ensure_one()
		grant = self._grant(tool.code)
		if not grant:
			return "denied", _("The agent has no grant for %s.", tool.name), grant
		if tool.supervisor_only and not self.is_supervisor:
			return "denied", _("Only a supervisor agent uses %s.", tool.name), grant
		risks = [r[0] for r in registry.RISKS]
		if risks.index(tool.risk) > risks.index(self.max_risk or "high"):
			return "denied", _("%s is riskier than this agent is allowed.", tool.name), grant
		level = min(int(self.authority_level), int(grant.level))
		companies = set(plan.company_ids or [])
		allowed_companies = set((grant.company_ids or self.company_ids).ids) & set(env.companies.ids)
		if companies - allowed_companies:
			return "denied", _("The record belongs to a company the agent may not work in."), grant
		if grant.model_ids and plan.model and plan.model not in grant.model_ids.mapped("model"):
			return "denied", _("The agent may not use %(tool)s on %(model)s.", tool=tool.name, model=plan.model), grant
		limit = min(a for a in (grant.max_amount, self.max_amount) if a) if (grant.max_amount or self.max_amount) else 0
		over_limit = bool(limit and plan.amount > limit)
		if tool.level <= level and not tool.sensitive and tool.level < 4:
			if over_limit and tool.level >= 3:
				return ("approval", _("The amount is over the agent's limit."), grant) if level >= 3 else (
					"denied", _("The amount is over the agent's limit."), grant)
			return "allowed", "", grant
		if tool.level == 4 or tool.sensitive:
			if level >= 4 and grant.auto_execute and grant._auto_allows(plan, over_limit):
				return "allowed", _("Automatic, by the rule set by %s.", grant.rule_set_by.name or ""), grant
			if level >= 3:
				return "approval", _("This action waits for a person's approval."), grant
			if level == 2:
				return "suggestion", _("At its authority the agent only suggests this action."), grant
			return "denied", _("At its authority the agent only reads and reports."), grant
		if tool.level == 3 and level == 2:
			return "suggestion", _("At its authority the agent only suggests this action."), grant
		return "denied", _("%s needs a higher authority than the agent has.", tool.name), grant

	# --- buttons

	def action_run_now(self):
		self.ensure_one()
		run = self.env["veron.ai.run"]._start(self, self.env.user, initiator="user")
		return run._open()

	def action_open_runs(self):
		self.ensure_one()
		return {"type": "ir.actions.act_window", "res_model": "veron.ai.run", "view_mode": "list,form",
			"name": _("Runs of %s", self.name), "domain": [("agent_id", "=", self.id)]}

	def action_open_approvals(self):
		self.ensure_one()
		return {"type": "ir.actions.act_window", "res_model": "veron.ai.approval", "view_mode": "list,form",
			"name": _("Approvals of %s", self.name), "domain": [("agent_id", "=", self.id)]}

	def action_open_chat(self):
		self.ensure_one()
		return {"type": "ir.actions.client", "tag": "veron_ai_agent.chat", "params": {"agent_id": self.id},
			"name": self.name}

	@api.model
	def _run_event(self, event_code, record=None, text=""):
		"""Starts the agents waiting for an event, e.g. from an automated action. The run has the rights of
		each agent's run-as user."""
		agents = self.sudo().search([("enabled", "=", True), ("trigger_event", "=", True)])
		runs = self.env["veron.ai.run"]
		for agent in agents:
			codes = [c.strip() for c in (agent.event_codes or "").split(",")]
			if event_code not in codes:
				continue
			user = agent.run_as_user_id or agent.responsible_user_id
			runs |= self.env["veron.ai.run"].sudo()._enqueue(agent, user, initiator="event", text=text or event_code,
				record=record)
		return runs


class AiAgentTool(models.Model):
	"""A tool granted to an agent, with its own authority and limits. Only a manager writes these."""

	_name = "veron.ai.agent.tool"
	_description = "Agent Tool Grant"
	_order = "agent_id, tool_id"

	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade", index=True)
	tool_id = fields.Many2one("veron.ai.tool", required=True, ondelete="cascade")
	active = fields.Boolean(default=True)
	tool_level = fields.Integer(related="tool_id.level")
	sensitive = fields.Selection(related="tool_id.sensitive")
	risk = fields.Selection(related="tool_id.risk")
	level = fields.Selection(registry.LEVEL_NAMES, "Authority", required=True, default="1",
		help="The authority of the agent for this tool; the lower of this and the agent's own applies")
	max_amount = fields.Float("Highest Amount")
	company_ids = fields.Many2many("res.company", string="Only in Companies")
	model_ids = fields.Many2many("ir.model", string="Only on Record Types")
	hour_from = fields.Float("From Hour", default=0.0)
	hour_to = fields.Float("To Hour", default=24.0)
	weekdays = fields.Char("Weekdays", help="Numbers of the weekdays, 0 for Monday to 6 for Sunday, e.g. 5,6,0,1,2; empty: every day")
	auto_execute = fields.Boolean("Act Automatically", help="At authority 4, act without asking, within these limits")
	requester_may_approve = fields.Boolean("The Person Who Asked May Approve",
		help="An action of this tool waiting for approval may be approved by the person who asked for it, with their own "
			"rights; never for a sensitive action")
	sensitive_rule = fields.Boolean("Explicit Rule for a Sensitive Action",
		help="Needed for a sensitive action (posting, payment, publishing...) to be done automatically")
	rule_note = fields.Char("Why")
	rule_valid_until = fields.Date("Rule Valid Until")
	rule_set_by = fields.Many2one("res.users", readonly=True)
	approver_user_ids = fields.Many2many("res.users", string="Approved By", domain=[("share", "=", False)],
		help="Who approves this tool's actions; empty: the responsible and the supervising person")

	_agent_tool = models.Constraint("unique (agent_id, tool_id)", "A tool is granted once to an agent.")

	@api.constrains("hour_from", "hour_to", "weekdays", "sensitive_rule", "rule_note", "level", "auto_execute")
	def _check(self):
		for grant in self:
			if not 0 <= grant.hour_from < grant.hour_to <= 24:
				raise ValidationError(_("The hours are between 0 and 24, the first before the second."))
			if grant.weekdays and not all(d.strip() in "0123456" and d.strip() for d in grant.weekdays.split(",")):
				raise ValidationError(_("The weekdays are numbers from 0 to 6, separated by commas."))
			if grant.sensitive_rule and not grant.rule_note:
				raise ValidationError(_("Write why the sensitive action may be done automatically."))
			if grant.auto_execute and grant.level != "4":
				raise ValidationError(_("Only at authority 4 does a tool act automatically."))

	@api.model_create_multi
	def create(self, vals_list):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		for vals in vals_list:
			if vals.get("sensitive_rule") or vals.get("auto_execute"):
				vals["rule_set_by"] = self.env.uid
		grants = super().create(vals_list)
		for grant in grants:
			self.env["veron.ai.audit"]._log("grant_changed", agent=grant.agent_id, tool=grant.tool_id.code,
				description=_("Granted %(tool)s at authority %(level)s", tool=grant.tool_id.name, level=grant.level))
		return grants

	def write(self, vals):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		if {"sensitive_rule", "auto_execute", "max_amount", "level", "rule_valid_until"} & set(vals):
			vals["rule_set_by"] = self.env.uid
		res = super().write(vals)
		for grant in self:
			self.env["veron.ai.audit"]._log("grant_changed", agent=grant.agent_id, tool=grant.tool_id.code,
				description=_("Grant of %s changed", grant.tool_id.name),
				data={k: v for k, v in vals.items() if k != "rule_set_by"})
		return res

	def unlink(self):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		return super().unlink()

	def _auto_allows(self, plan, over_limit):
		"""The limits of automatic action: amount, hours, weekdays, rule and its validity"""
		self.ensure_one()
		if over_limit:
			return False
		if self.sensitive and not self.sensitive_rule:
			return False
		if self.rule_valid_until and self.rule_valid_until < fields.Date.context_today(self):
			return False
		tz = pytz.timezone(self.agent_id.tz or "Asia/Tehran")
		now = datetime.now(tz)
		hour = now.hour + now.minute / 60
		if not self.hour_from <= hour < self.hour_to:
			return False
		if self.weekdays and str(now.weekday()) not in [d.strip() for d in self.weekdays.split(",")]:
			return False
		return True

	def _approvers(self):
		self.ensure_one()
		return self.approver_user_ids or (self.agent_id.responsible_user_id | self.agent_id.supervisor_user_id)


class AiAgentScope(models.Model):
	"""A model the agent may read, with the records (domain) and the fields it may see"""

	_name = "veron.ai.agent.scope"
	_description = "Agent Data Scope"

	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade", index=True)
	model_id = fields.Many2one("ir.model", "Data", required=True, ondelete="cascade")
	model = fields.Char(related="model_id.model")
	domain = fields.Char("Only Records", default="[]", help="An Odoo domain, e.g. [('company_id', '=', company_id)]")
	field_ids = fields.Many2many("ir.model.fields", string="Only Fields", domain="[('model_id', '=', model_id)]")
	note = fields.Char()

	_agent_model = models.Constraint("unique (agent_id, model_id)", "A model is in an agent's data once.")

	def _eval_context(self, env):
		return {"user": env.user, "uid": env.uid, "company_id": env.company.id, "company_ids": env.companies.ids,
			"context_today": lambda: fields.Date.context_today(env.user)}

	def _domain(self, env):
		self.ensure_one()
		value = safe_eval(self.domain or "[]", self._eval_context(env))
		return Domain(value)

	@api.constrains("domain", "model_id")
	def _check_domain(self):
		for scope in self:
			try:
				domain = scope._domain(self.env)
				self.env[scope.model_id.model].search(domain, limit=1)
			except Exception as error:
				raise ValidationError(_("The domain of %(model)s is not valid: %(error)s", model=scope.model_id.name,
					error=error)) from error

	@api.model_create_multi
	def create(self, vals_list):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		return super().create(vals_list)

	def write(self, vals):
		if self.env.context.get("veron_ai_run_id"):
			raise in_run(self.env)
		return super().write(vals)


class ResUsers(models.Model):
	_inherit = "res.users"

	veron_ai_service_user = fields.Boolean("Agent Service User",
		help="A user agents run as; it never approves an agent's action")
