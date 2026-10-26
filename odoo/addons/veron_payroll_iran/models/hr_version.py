from odoo import api, fields, models


class HrVersion(models.Model):
	_inherit = "hr.version"

	veron_seniority = fields.Monetary("Seniority Wage", tracking=True,
		help="The seniority wage (پایه سنوات) of a month, the sum of the years of work")
	veron_other_allowance = fields.Monetary("Other Allowances", tracking=True,
		help="Allowances of a month beyond those of the law, as responsibility or commuting")
	veron_insured = fields.Boolean("Social Security", default=True, tracking=True,
		help="The wage is insured with the Social Security Organization")
	veron_insurance_number = fields.Char("Insurance Number", tracking=True)

	@api.model
	def _get_whitelist_fields_from_template(self):
		return super()._get_whitelist_fields_from_template() + ["veron_seniority", "veron_other_allowance", "veron_insured"]
