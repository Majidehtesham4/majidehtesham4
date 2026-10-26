from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

# Mehr 1405
MEHR = ("2026-09-23", "2026-10-22")


@tagged("post_install", "-at_install")
class TestPayrollIran(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env.user.group_ids |= cls.env.ref("payroll.group_payroll_manager") | cls.env.ref("account.group_account_invoice")
		cls.rates = cls.env.ref("veron_payroll_iran.payroll_year_1405")
		cls.structure = cls.env.ref("veron_payroll_iran.structure_iran")
		cls.employee = cls.env["hr.employee"].create({"name": "کارمند آزمایشی", "marital": "married", "children": 2})
		cls.employee.version_id.write({
			"date_version": "2026-01-01", "contract_date_start": "2026-01-01", "wage": 600000000,
			"veron_seniority": 3000000, "struct_id": cls.structure.id,
		})

	def payslip(self, **inputs):
		payslip = self.env["hr.payslip"].create({"employee_id": self.employee.id, "date_from": MEHR[0], "date_to": MEHR[1]})
		payslip.onchange_employee()
		payslip.date_from, payslip.date_to = MEHR
		for line in payslip.input_line_ids:
			if line.code in inputs:
				line.amount = inputs[line.code]
		return payslip

	def lines(self, payslip):
		return {line.code: line.total for line in payslip.line_ids}

	def test_rates_must_be_confirmed(self):
		self.assertEqual(self.rates.state, "draft")
		with self.assertRaises(UserError):
			self.payslip().compute_sheet()
		self.rates.action_confirm()
		with self.assertRaises(UserError):
			self.rates.min_monthly = 1
		self.rates.action_draft()
		self.rates.min_monthly = 166250000

	def test_tax_brackets(self):
		self.assertEqual(self.rates.tax(400000000), 0)
		self.assertEqual(self.rates.tax(800000000), 40000000)
		# 40M + 15% of 200M + 20% of 200M + 25% of 200M + 30% of 100M
		self.assertEqual(self.rates.tax(1500000000), 40000000 + 30000000 + 40000000 + 50000000 + 30000000)

	def test_full_month(self):
		self.rates.action_confirm()
		payslip = self.payslip(OVERTIME=10)
		payslip.compute_sheet()
		lines = self.lines(payslip)
		self.assertAlmostEqual(lines["BASE"], 600000000, places=0)
		self.assertEqual(lines["HOUSING"], 30000000)
		self.assertEqual(lines["CHILD"], 33250000)
		self.assertEqual(lines["MARRIAGE"], 5000000)
		overtime = round(600000000 / 220 * 1.4) * 10
		self.assertEqual(lines["OVERTIME"], overtime)
		gross = 600000000 + 3000000 + 30000000 + 22000000 + 33250000 + 5000000 + overtime
		self.assertAlmostEqual(lines["GROSS"], gross, places=0)
		insurable = gross - 33250000
		self.assertEqual(lines["INS_EMP"], -round(insurable * 0.07))
		taxable = gross - insurable * 0.02
		self.assertEqual(lines["TAX"], -self.rates.tax(taxable))
		self.assertAlmostEqual(lines["NET"], gross + lines["INS_EMP"] + lines["TAX"], places=0)
		self.assertEqual(lines["INS_ER"], round(insurable * 0.2))
		self.assertEqual(lines["EIDI"], round(166250000 * 3 / 12))
		self.assertIn("مهر 1405", payslip.name)

		payslip.action_payslip_done()
		move = payslip.veron_move_id
		self.assertEqual(move.state, "draft")
		self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit")), places=0)
		payable = move.line_ids.filtered(lambda l: l.account_id.code == "211208")
		self.assertAlmostEqual(payable.credit, lines["NET"], places=0)
		self.assertEqual(payable.partner_id, self.employee.work_contact_id)
		insurance = move.line_ids.filtered(lambda l: l.account_id.code == "211204")
		self.assertAlmostEqual(sum(insurance.mapped("credit")), -lines["INS_EMP"] + lines["INS_ER"] + lines["INS_UN"], places=0)

	def test_absence_and_ceiling(self):
		self.rates.action_confirm()
		payslip = self.payslip(ABSENCE=3)
		payslip.compute_sheet()
		lines = self.lines(payslip)
		self.assertAlmostEqual(lines["BASE"], 600000000 / 30 * 27, places=0)
		self.assertEqual(lines["HOUSING"], 27000000)
		# A wage over the ceiling is insured up to the ceiling
		self.employee.version_id.wage = 2000000000
		payslip.compute_sheet()
		self.assertEqual(self.lines(payslip)["INS_EMP"], -round(1163750000 / 30 * 27 * 0.07))

	def test_minimum_wage(self):
		self.rates.action_confirm()
		self.employee.version_id.wage = 100000000
		with self.assertRaises(UserError):
			self.payslip().compute_sheet()
