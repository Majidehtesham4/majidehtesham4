from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import registry

# The roles a team of each supervisor starts with; a person adds or takes away the parts
TEAMS = {
	"sup_finance": ["fin_periodic_report", "fin_sale_invoice_draft", "fin_bill_draft", "fin_receivables",
		"fin_bank_matching", "fin_documents_check"],
	"sup_operations": ["stk_alerts", "pur_late_followup", "pur_mismatch", "sal_quote_followup", "sal_customer_summary",
		"ops_tasks"],
}


class TeamWizard(models.TransientModel):
	"""A supervisor and its team made in one go: the person picks the parts (roles) it is made of, sees what each
	may read and do, and confirms; the supervisor then gives each task to the part that has its tool"""

	_name = "veron.ai.team.wizard"
	_inherit = ["veron.ai.guide.mixin"]
	_description = "Build an Agent Team"

	supervisor_template_id = fields.Many2one("veron.ai.agent.template", "Supervisor", required=True,
		domain=[("is_supervisor", "=", True)], default=lambda self: self.env.ref("veron_ai_agent.role_sup_finance",
		raise_if_not_found=False))
	name = fields.Char("Name of the Supervisor", required=True, compute="_compute_name", store=True, readonly=False,
		precompute=True)
	member_template_ids = fields.Many2many("veron.ai.agent.template", string="Parts of the Team",
		domain=[("is_supervisor", "=", False)], compute="_compute_members", store=True,
		readonly=False, precompute=True)
	authority_level = fields.Selection(registry.LEVEL_NAMES, "Authority", required=True, default="3",
		help="The same for every part; what changes data always waits for a person's approval")
	company_ids = fields.Many2many("res.company", string="Companies", required=True, default=lambda self: self.env.company)
	responsible_user_id = fields.Many2one("res.users", "Responsible", required=True, default=lambda self: self.env.user,
		domain=[("share", "=", False)])
	supervisor_user_id = fields.Many2one("res.users", "Supervising Person", domain=[("share", "=", False)])
	enable = fields.Boolean("Turn the Team On Now", default=True)
	explanation = fields.Html(compute="_compute_explanation", sanitize=False)
	understood = fields.Boolean("I have read what each part may read and do")

	@api.depends("supervisor_template_id")
	def _compute_name(self):
		for wizard in self:
			wizard.name = wizard.supervisor_template_id.name

	@api.depends("supervisor_template_id")
	def _compute_members(self):
		Template = self.env["veron.ai.agent.template"]
		for wizard in self:
			codes = TEAMS.get(wizard.supervisor_template_id.code, [])
			wizard.member_template_ids = Template.search([("code", "in", codes)]).filtered("available")

	@api.depends("member_template_ids", "authority_level")
	def _compute_explanation(self):
		Agent = self.env["veron.ai.agent"]
		for wizard in self:
			level = int(wizard.authority_level or 1)
			parts = []
			for template in wizard.member_template_ids:
				names = self.env["ir.model"].sudo().search([("model", "in", template._scope_model_names())]).mapped("name")
				parts.append(Markup("<div class='mb-3'><b>%s</b><div class='text-muted'>%s</div><div>%s</div>"
					"<div class='small'>%s: %s</div></div>") % (template.name, template.description or "",
					Agent._explain(template.tool_ids, level), _("Reads"), ", ".join(names) or "-"))
			wizard.explanation = Markup("").join(parts) or Markup("<p>%s</p>") % _("Add at least one part.")

	def action_create(self):
		self.ensure_one()
		if not self.understood:
			raise UserError(_("Read what each part may do and tick the box."))
		if not self.member_template_ids:
			raise UserError(_("Add at least one part to the team."))
		Agent = self.env["veron.ai.agent"]
		level = self.authority_level
		# Parts already made of the same role are taken into the team rather than made twice
		supervisor = Agent.search([("template_id", "=", self.supervisor_template_id.id), ("name", "=", self.name)],
			limit=1) or self.supervisor_template_id._make_agent(self.name, self.company_ids, self.responsible_user_id,
			self.supervisor_user_id, level)
		members = Agent
		for template in self.member_template_ids:
			if not template.available:
				raise UserError(_("The part «%(part)s» needs: %(missing)s. Install it first.", part=template.name,
					missing=template.missing))
			member = Agent.search([("template_id", "=", template.id), ("supervisor_agent_id", "in", [supervisor.id, False])],
				limit=1) or template._make_agent(template.name, self.company_ids, self.responsible_user_id,
				self.supervisor_user_id, level)
			members |= member
		members.write({"supervisor_agent_id": supervisor.id})
		supervisor.write({"delegate_agent_ids": [(4, member.id) for member in members]})
		if self.enable:
			(supervisor | members).write({"enabled": True})
		return {"type": "ir.actions.act_window", "res_model": "veron.ai.agent", "res_id": supervisor.id, "view_mode": "form"}
