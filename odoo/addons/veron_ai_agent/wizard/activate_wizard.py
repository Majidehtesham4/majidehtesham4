from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import registry


class ActivateWizard(models.TransientModel):
	"""Turning a role into a working agent: what it will read and do is shown before it is made"""

	_name = "veron.ai.activate.wizard"
	_description = "Activate an Agent Role"

	template_id = fields.Many2one("veron.ai.agent.template", required=True)
	name = fields.Char(required=True, compute="_compute_name", store=True, readonly=False, precompute=True)
	company_ids = fields.Many2many("res.company", string="Companies", required=True, default=lambda self: self.env.company)
	responsible_user_id = fields.Many2one("res.users", "Responsible", required=True, default=lambda self: self.env.user,
		domain=[("share", "=", False)])
	supervisor_user_id = fields.Many2one("res.users", "Supervising Person", domain=[("share", "=", False)])
	authority_level = fields.Selection(registry.LEVEL_NAMES, "Authority", required=True)
	available = fields.Boolean(related="template_id.available")
	missing = fields.Char(related="template_id.missing")
	description = fields.Text(related="template_id.description")
	explanation = fields.Html(compute="_compute_explanation", sanitize=False)
	data_models = fields.Char("Data It Reads", compute="_compute_explanation")
	understood = fields.Boolean("I have read what this agent may read and do")

	@api.depends("template_id")
	def _compute_name(self):
		for wizard in self:
			wizard.name = wizard.template_id.name

	@api.onchange("template_id")
	def _onchange_template(self):
		self.authority_level = self.template_id.default_level or "1"

	@api.depends("template_id", "authority_level")
	def _compute_explanation(self):
		for wizard in self:
			level = int(wizard.authority_level or wizard.template_id.default_level or 1)
			wizard.explanation = self.env["veron.ai.agent"]._explain(wizard.template_id.tool_ids, level)
			models_used = wizard.template_id._scope_model_names()
			names = self.env["ir.model"].search([("model", "in", models_used)]).mapped("name")
			wizard.data_models = ", ".join(names)

	def action_create(self):
		self.ensure_one()
		template = self.template_id
		if not template.available:
			raise UserError(_("This role needs: %s. Install it first.", template.missing))
		if not self.understood:
			raise UserError(_("Read what the agent may do and tick the box."))
		agent = template._make_agent(self.name, self.company_ids, self.responsible_user_id, self.supervisor_user_id,
			self.authority_level)
		return {"type": "ir.actions.act_window", "res_model": "veron.ai.agent", "res_id": agent.id, "view_mode": "form"}
