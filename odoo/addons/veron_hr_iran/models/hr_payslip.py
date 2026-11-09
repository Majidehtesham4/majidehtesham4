from odoo import _, fields, models

from odoo.addons.veron_core.models import jalali

# The inputs filled from the records of this module
AUTO = {
	"LOAN": "قسط وام", "ADVANCE": "مساعده", "ABSENCE": "غیبت و مرخصی بدون حقوق (روز)", "MISSION": "فوق‌العاده مأموریت",
	"INS_SUPP": "بیمه تکمیلی سهم کارمند", "INS_LIFE": "بیمه عمر سهم کارمند",
}


class HrPayslipInput(models.Model):
	_inherit = "hr.payslip.input"

	veron_auto = fields.Boolean("Filled From the Records", help="Filled again at each computation; typed by hand, it stays")

	def write(self, vals):
		if "amount" in vals and not self.env.context.get("veron_auto_input"):
			# Typed by hand: the records do not change it any more
			vals = dict(vals, veron_auto=False)
		return super().write(vals)


class HrPayslip(models.Model):
	_inherit = "hr.payslip"

	veron_loan_line_ids = fields.One2many("veron.hr.loan.line", "payslip_id", "Instalments Deducted")

	def _veron_overlaps(self, start, end):
		return (not start or start <= self.date_to) and (not end or end >= self.date_from)

	def _veron_records(self):
		"""What the records of the month give each input, and the loan instalments taken"""
		self.ensure_one()
		employee = self.employee_id
		lines = self.env["veron.hr.loan.line"].search([("employee_id", "=", employee.id), ("loan_id.state", "in", ("approved", "paid")),
			("date", ">=", self.date_from), ("date", "<=", self.date_to), "|", "|", ("payslip_id", "=", False),
			("payslip_id", "=", self.id), ("payslip_id.state", "=", "cancel")])
		missions = self.env["veron.hr.mission"].search([("employee_id", "=", employee.id), ("state", "=", "approved"),
			("date_to", ">=", self.date_from), ("date_to", "<=", self.date_to)])
		absences = self.env["veron.hr.absence"].search([("employee_id", "=", employee.id), ("state", "=", "approved"),
			("date", ">=", self.date_from), ("date", "<=", self.date_to)])
		members = employee.veron_insurance_ids.filtered(lambda m: m.plan_id.active and self._veron_overlaps(m.date_from, m.date_to)
			and self._veron_overlaps(m.plan_id.date_from, m.plan_id.date_to))
		values = {
			"LOAN": sum(lines.filtered(lambda l: l.kind == "loan").mapped("amount")),
			"ADVANCE": sum(lines.filtered(lambda l: l.kind == "advance").mapped("amount")),
			"ABSENCE": sum(absences.mapped("days")),
			"MISSION": sum(missions.mapped("amount")),
			"INS_SUPP": sum(members.filtered(lambda m: m.kind == "supplementary").mapped("amount")),
			"INS_LIFE": sum(members.filtered(lambda m: m.kind == "life").mapped("amount")),
		}
		return values, lines

	def _veron_fill_inputs(self):
		for slip in self.filtered(lambda s: s.state in ("draft", "verify")):
			values, lines = slip._veron_records()
			contract = slip.contract_id if "contract_id" in slip._fields and slip.contract_id else slip.employee_id.version_id
			for code, amount in values.items():
				line = slip.input_line_ids.filtered(lambda l, c=code: l.code == c)[:1]
				if line:
					if line.veron_auto or not line.amount:
						line.with_context(veron_auto_input=True).write({"amount": amount, "veron_auto": True})
				elif amount:
					slip.input_line_ids = [(0, 0, {"name": AUTO[code], "code": code, "amount": amount, "veron_auto": True,
						"contract_id": contract.id})]
			# The instalments are this payslip's; done, they are paid
			(slip.veron_loan_line_ids - lines).write({"payslip_id": False})
			lines.write({"payslip_id": slip.id})

	def compute_sheet(self):
		for slip in self.filtered(lambda s: s.state in ("draft", "verify")):
			year = jalali.to_jalali(slip.date_from)[0]
			contracts = slip.contract_id if "contract_id" in slip._fields and slip.contract_id else slip.employee_id.version_id
			contracts._veron_check_group_wage(year)
		self._veron_fill_inputs()
		return super().compute_sheet()

	def action_payslip_done(self):
		result = super().action_payslip_done()
		self.veron_loan_line_ids.loan_id._check_paid()
		return result

	def action_payslip_cancel(self):
		loans = self.veron_loan_line_ids.loan_id
		result = super().action_payslip_cancel()
		loans._check_paid()
		return result
