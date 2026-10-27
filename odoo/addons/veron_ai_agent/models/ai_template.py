import json

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services import registry

CATEGORIES = [
	("finance", "Finance and Accounting"),
	("purchase", "Purchase and Inventory"),
	("sales", "Sales, Customers and Website"),
	("hr", "Human Resources and Operations"),
	("coordination", "Coordination"),
]
SCHEDULES = [("manual", "Manual"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]


class AiAgentTemplate(models.Model):
	_name = "veron.ai.agent.template"
	_description = "Agent Role"
	_order = "category, sequence, id"

	code = fields.Char(required=True, index=True)
	name = fields.Char(required=True, translate=True)
	category = fields.Selection(CATEGORIES, required=True, default="finance")
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	description = fields.Text("What It Does", translate=True)
	goal = fields.Text(translate=True)
	instructions = fields.Text("Working Instructions", translate=True,
		help="How the agent works. No law, rate or tax rule belongs here: those come from the modules' own data.")
	tool_codes = fields.Char("Tools", help="The codes of its tools, separated by commas")
	tool_ids = fields.Many2many("veron.ai.tool", compute="_compute_tool_ids")
	default_level = fields.Selection(registry.LEVEL_NAMES, "Default Authority", default="1", required=True)
	is_supervisor = fields.Boolean("Supervisor")
	schedule_type = fields.Selection(SCHEDULES, "Default Schedule", default="manual", required=True)
	schedule_hour = fields.Float("At", default=8.0)
	playbook = fields.Text("Steps (JSON)", help='Steps run before the model, e.g. [{"tool": "sales_summary", "args": {"days": 1}}]')
	expected_output = fields.Text(translate=True)
	required_modules = fields.Char("Needs Modules", help="Technical names of the modules its tools need")
	scope_models = fields.Char("Data It Reads", help="Technical names of the models it reads, separated by commas")
	available = fields.Boolean(compute="_compute_available")
	missing = fields.Char("Missing", compute="_compute_available")
	explanation = fields.Html(compute="_compute_explanation", sanitize=False)
	agent_ids = fields.One2many("veron.ai.agent", "template_id")
	agent_count = fields.Integer(compute="_compute_agent_count")

	_code_unique = models.Constraint("unique (code)", "A role code is unique.")

	@api.depends("tool_codes")
	def _compute_tool_ids(self):
		for template in self:
			template.tool_ids = self.env["veron.ai.tool"]._by_codes(template.tool_codes)

	def _tool_codes(self):
		return [c.strip() for c in (self.tool_codes or "").split(",") if c.strip()]

	@api.depends("tool_codes", "required_modules")
	def _compute_available(self):
		installed = set(self.env["ir.module.module"].sudo().search([("state", "=", "installed")]).mapped("name"))
		for template in self:
			missing = []
			for code in template._tool_codes():
				tool = registry.get(code)
				if not tool:
					missing.append(code)
				elif not tool.available(self.env):
					missing.extend(model for model in tool.models if model not in self.env)
			modules = [m.strip() for m in (template.required_modules or "").split(",") if m.strip()]
			missing_modules = [m for m in modules if m not in installed]
			template.available = not missing and not missing_modules
			template.missing = ", ".join(sorted(set(missing_modules + missing)))

	def _compute_agent_count(self):
		for template in self:
			template.agent_count = len(template.agent_ids)

	@api.constrains("playbook")
	def _check_playbook(self):
		for template in self:
			steps = template._steps()
			for step in steps:
				if not isinstance(step, dict) or "tool" not in step or not isinstance(step.get("args", {}), dict):
					raise ValidationError(_("Each step is an object with a tool and its args."))
				if step["tool"] not in template._tool_codes():
					raise ValidationError(_("The step tool %s is not among the role's tools.", step["tool"]))

	def _steps(self):
		if not self.playbook:
			return []
		try:
			steps = json.loads(self.playbook)
		except ValueError as error:
			raise ValidationError(_("The steps are not valid JSON.")) from error
		if not isinstance(steps, list):
			raise ValidationError(_("The steps are a JSON list."))
		return steps

	@api.depends("tool_codes", "default_level")
	def _compute_explanation(self):
		for template in self:
			template.explanation = self.env["veron.ai.agent"]._explain(template.tool_ids, int(template.default_level))

	def action_activate(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"res_model": "veron.ai.activate.wizard",
			"view_mode": "form",
			"target": "new",
			"name": _("Activate %s", self.name),
			"context": {"default_template_id": self.id},
		}

	def action_open_agents(self):
		self.ensure_one()
		return {"type": "ir.actions.act_window", "res_model": "veron.ai.agent", "view_mode": "list,form",
			"name": self.name, "domain": [("template_id", "=", self.id)], "context": {"default_template_id": self.id}}


def explain_tools(env, tools, level):
	"""A plain explanation of what an agent with these tools at this level may and may not do"""
	labels = dict(registry.LEVEL_NAMES)
	rows = []
	for tool in tools:
		if tool.level <= level and not tool.sensitive:
			what = _("does it")
		elif tool.sensitive or tool.level == 4:
			what = _("asks a person to approve") if level >= 3 else (_("only suggests") if level >= 2 else _("may not"))
		elif tool.level == 3:
			what = _("only suggests") if level == 2 else _("may not")
		else:
			what = _("may not")
		models_used = f" ({escape(tool.models_used)})" if tool.models_used else ""
		rows.append(Markup("<li><b>%s</b>%s: %s</li>") % (tool.name, models_used, what))
	return Markup("<p>%s</p><ul>%s</ul>") % (_("Authority: %s", labels[str(level)]), Markup("").join(rows))


class AiAgentTemplateMake(models.Model):
	_inherit = "veron.ai.agent.template"

	def _scope_model_names(self):
		self.ensure_one()
		names = [m.strip() for m in (self.scope_models or "").split(",") if m.strip()]
		for code in self._tool_codes():
			tool = registry.get(code)
			if tool:
				names += list(tool.models)
		return [name for name in dict.fromkeys(names) if name in self.env]

	def _make_agent(self, name, companies, responsible, supervisor, level):
		"""An agent of the role, not yet working: a manager checks it and turns it on"""
		self.ensure_one()
		Model = self.env["ir.model"]
		tools = self.env["veron.ai.tool"]._by_codes(self.tool_codes)
		agent = self.env["veron.ai.agent"].create({
			"name": name, "template_id": self.id, "goal": self.goal, "description": self.description,
			"instructions": self.instructions, "playbook": self.playbook, "expected_output": self.expected_output,
			"company_ids": [(6, 0, companies.ids)], "company_id": companies[:1].id, "responsible_user_id": responsible.id,
			"supervisor_user_id": supervisor.id if supervisor else False, "authority_level": level,
			"is_supervisor": self.is_supervisor, "enabled": False,
			"trigger_schedule": self.schedule_type != "manual",
			"notify_user_ids": [(6, 0, (responsible | (supervisor or responsible)).ids)],
			"grant_ids": [(0, 0, {"tool_id": tool.id, "level": level}) for tool in tools],
			"scope_ids": [(0, 0, {"model_id": Model._get_id(model)}) for model in self._scope_model_names()],
		})
		if self.schedule_type != "manual":
			self.env["veron.ai.schedule"].create({"agent_id": agent.id, "name": self.name, "interval": self.schedule_type,
				"hour": self.schedule_hour, "input_text": self.expected_output or False})
		return agent
