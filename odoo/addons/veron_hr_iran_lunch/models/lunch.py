from odoo import fields, models

from odoo.addons.veron_hr_iran.models import hr_payslip as base

base.AUTO["MEAL"] = "کسر هزینه غذا"


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_lunch_share = fields.Float("Employee's Share of Lunch (%)", default=100.0,
		help="The share of the cost of the lunches ordered that is deducted from the payslip")


class HrPayslip(models.Model):
	_inherit = "hr.payslip"

	def _veron_records(self):
		values, lines = super()._veron_records()
		user = self.employee_id.user_id
		orders = self.env["lunch.order"].sudo().search([("user_id", "=", user.id), ("date", ">=", self.date_from),
			("date", "<=", self.date_to), ("state", "in", ("confirmed", "sent"))]) if user else []
		share = (self.company_id or self.env.company).veron_lunch_share / 100
		values["MEAL"] = round(sum(order.price for order in orders) * share)
		return values, lines
