from unittest.mock import patch

import frappe
from erpnext.accounts.utils import get_balance_on
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from iran_erp import onboarding
from iran_erp.demo import opening_account


class TestEasySetup(IntegrationTestCase):
	"""The whole setup, from the business questions to the recorded opening balances."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.company = onboarding._company()
		setup = frappe.get_single("Iran Setup")
		setup.update({"data": "{}", "steps_done": "[]", "opening_posted": 0, "opening_documents": None})
		setup.save()

	def save(self, step, values):
		return onboarding.save_step(step, values)

	def test_setup_and_opening_balances(self):
		state = self.save(
			"business",
			{
				"business_type": "Shop",
				"sells": "Goods",
				"has_warehouse": 1,
				"vat_registered": 1,
				"uses_cheques": 1,
				"opening_date": nowdate(),
			},
		)
		self.assertIn("business", [s["key"] for s in state["steps"] if s["done"]])
		self.save(
			"banks",
			{
				"cash_balance": 10_000_000,
				"banks": [{"bank": "بانک آزمون راه‌اندازی", "account_name": "جاری", "balance": 100_000_000}],
			},
		)
		self.save("warehouses", {"warehouses": [{"warehouse_name": "انبار آزمون راه‌اندازی"}]})
		self.save(
			"customers",
			{
				"customers": [
					{"name": "مشتری آزمون راه‌اندازی", "mobile": "09121234567", "balance": 50_000_000},
					{"name": "مشتری پیش‌پرداخت آزمون", "balance": -5_000_000},
				]
			},
		)
		self.save("suppliers", {"suppliers": [{"name": "تأمین‌کننده آزمون راه‌اندازی", "balance": 30_000_000}]})
		self.save(
			"items",
			{
				"items": [
					{
						"item_name": "کالای آزمون راه‌اندازی",
						"selling_price": 1_500_000,
						"cost_price": 1_000_000,
						"qty": 2,
						"warehouse": "انبار آزمون راه‌اندازی",
					},
					{"item_name": "خدمت آزمون راه‌اندازی", "selling_price": 800_000, "is_service": 1},
				]
			},
		)
		self.save(
			"cheques",
			{
				"cheques": [
					{
						"direction": "دریافتی",
						"party": "مشتری آزمون راه‌اندازی",
						"amount": 20_000_000,
						"due_date": nowdate(),
						"number": "778899",
					}
				]
			},
		)

		review = onboarding.get_review()
		# 10 + 100 + (50 - 5) + 20 + 2 × 1 - 30
		self.assertEqual(review["capital"], 147_000_000)
		self.assertTrue(review["can_post"], review["issues"])

		with patch.object(frappe.db, "commit"):
			result = onboarding.post_opening()
		self.assertTrue(result["opening_posted"])
		made = {d["doctype"] for d in result["opening_documents"]}
		self.assertTrue(
			{"Journal Entry", "Sales Invoice", "Purchase Invoice", "Stock Reconciliation", "Iran Cheque"}
			<= made
		)

		date = nowdate()
		self.assertEqual(flt(get_balance_on(account=opening_account(self.company), date=date)), 0)
		ledger = frappe.db.get_value(
			"Account", {"company": self.company, "account_name": "بانک آزمون راه‌اندازی جاری"}
		)
		self.assertEqual(flt(get_balance_on(account=ledger, date=date)), 100_000_000)
		customer = frappe.db.get_value("Customer", {"customer_name": "مشتری آزمون راه‌اندازی"})
		# 50 owed plus the 20 cheque on the opening invoice, less the 20 cheque registered against it
		self.assertEqual(
			flt(get_balance_on(party_type="Customer", party=customer, company=self.company, date=date)),
			50_000_000,
		)
		item = frappe.db.get_value("Item", {"item_name": "کالای آزمون راه‌اندازی"})
		self.assertEqual(
			flt(frappe.db.get_value("Bin", {"item_code": item}, "actual_qty")),
			2,
		)
		# Nothing more can be recorded twice
		self.assertRaises(frappe.ValidationError, onboarding.post_opening)

	def test_bad_rows_are_reported(self):
		self.save("business", {"sells": "Goods", "has_warehouse": 1, "opening_date": nowdate()})
		self.assertRaises(
			frappe.ValidationError,
			self.save,
			"items",
			{"items": [{"item_name": "کالای بی‌قیمت آزمون", "qty": 3}]},
		)
		self.assertRaises(
			frappe.ValidationError,
			self.save,
			"customers",
			{"customers": [{"name": "مشتری موبایل غلط", "mobile": "12345"}]},
		)

	def test_services_business_skips_stock_steps(self):
		state = self.save("business", {"sells": "Services", "uses_cheques": 0, "opening_date": nowdate()})
		keys = [s["key"] for s in state["steps"]]
		self.assertNotIn("warehouses", keys)
		self.assertNotIn("cheques", keys)
		self.assertIn("items", keys)
