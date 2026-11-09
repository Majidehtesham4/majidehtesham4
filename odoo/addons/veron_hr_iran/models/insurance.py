from odoo import api, fields, models


class HrInsurancePlan(models.Model):
	"""A supplementary health or a life insurance contract of the company, with what an employee pays a month"""

	_name = "veron.hr.insurance.plan"
	_description = "Supplementary or Life Insurance Plan"
	_order = "kind, name"

	name = fields.Char(required=True)
	kind = fields.Selection([("supplementary", "Supplementary Health"), ("life", "Life")], required=True,
		default="supplementary")
	insurer_id = fields.Many2one("res.partner", "Insurer")
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	currency_id = fields.Many2one(related="company_id.currency_id")
	employee_share = fields.Monetary("Employee's Share a Month", help="For the employee and for each person insured")
	company_share = fields.Monetary("Company's Share a Month", help="For each person insured; not deducted")
	date_from = fields.Date()
	date_to = fields.Date()
	active = fields.Boolean(default=True)


class HrInsuranceMember(models.Model):
	"""An employee in a plan, with the people of the family insured with them"""

	_name = "veron.hr.insurance.member"
	_description = "Employee in an Insurance Plan"

	employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
	plan_id = fields.Many2one("veron.hr.insurance.plan", required=True)
	kind = fields.Selection(related="plan_id.kind", store=True)
	currency_id = fields.Many2one(related="plan_id.currency_id")
	dependants = fields.Integer("Family Members Insured", default=0)
	date_from = fields.Date()
	date_to = fields.Date()
	amount = fields.Monetary("Deducted a Month", compute="_compute_amount")

	@api.depends("plan_id.employee_share", "dependants")
	def _compute_amount(self):
		for member in self:
			member.amount = member.plan_id.employee_share * (1 + max(member.dependants, 0))
