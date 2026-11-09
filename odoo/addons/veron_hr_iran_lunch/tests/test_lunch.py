from odoo.tests import TransactionCase, tagged

MEHR = ("2026-09-23", "2026-10-22")


@tagged("post_install", "-at_install")
class TestLunchPayroll(TransactionCase):
	def test_lunches_deducted(self):
		self.env.user.group_ids |= self.env.ref("payroll.group_payroll_manager") | self.env.ref("lunch.group_lunch_manager")
		rates = self.env.ref("veron_payroll_iran.payroll_year_1405")
		if rates.state == "draft":
			rates.action_confirm()
		user = self.env["res.users"].create({"name": "کارمند ناهار", "login": "veron_lunch_user",
			"group_ids": [(6, 0, self.env.ref("base.group_user").ids)]})
		employee = self.env["hr.employee"].create({"name": "کارمند ناهار", "user_id": user.id})
		employee.version_id.write({"date_version": "2026-01-01", "contract_date_start": "2026-01-01", "wage": 600000000,
			"struct_id": self.env.ref("veron_payroll_iran.structure_iran").id})
		supplier = self.env["lunch.supplier"].create({"name": "رستوران", "partner_id": self.env["res.partner"].create({"name": "رستوران"}).id})
		product = self.env["lunch.product"].create({"name": "چلوکباب", "price": 2_000_000, "supplier_id": supplier.id,
			"category_id": self.env["lunch.product.category"].create({"name": "غذا"}).id})
		for day in ("2026-10-01", "2026-10-02"):
			order = self.env["lunch.order"].create({"product_id": product.id, "user_id": user.id, "date": day})
			order.state = "confirmed"
		self.env.company.veron_lunch_share = 50
		slip = self.env["hr.payslip"].create({"employee_id": employee.id, "date_from": MEHR[0], "date_to": MEHR[1]})
		slip.onchange_employee()
		slip.compute_sheet()
		self.assertEqual({line.code: line.total for line in slip.line_ids}["MEAL"], -2_000_000, "half of two lunches")
