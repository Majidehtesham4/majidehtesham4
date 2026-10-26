from odoo import fields, models


class HrSalaryRule(models.Model):
	_inherit = "hr.salary.rule"

	veron_debit_code = fields.Char("Debit Account Code", help="The account of the Iranian chart the amount is debited to, as 611001")
	veron_credit_code = fields.Char("Credit Account Code", help="The account the amount is credited to, as 211208")
	veron_partner = fields.Boolean("Employee as Partner", help="The employee is the partner of the line, as on salaries payable")
