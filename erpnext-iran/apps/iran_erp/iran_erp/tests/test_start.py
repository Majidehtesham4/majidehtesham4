import frappe
from frappe.tests import IntegrationTestCase

from iran_erp.start import WIZARDS, get_summary, get_wizard, run_wizard


class TestStartPage(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_every_wizard_has_fields(self):
		for intent in WIZARDS:
			wizard = get_wizard(intent)
			self.assertTrue(wizard["fields"], intent)
			# Every detail the command requires is asked for
			names = {f["fieldname"] for f in wizard["fields"]}
			from iran_erp.commands.engine import INTENT_BY_NAME

			for slot, _type, required, _question in INTENT_BY_NAME[intent].get("slots") or []:
				if required:
					self.assertIn(slot, names, f"{intent}: {slot}")

	def test_sales_invoice_from_form(self):
		customer = frappe.get_all("Customer", filters={"disabled": 0}, pluck="name", limit=1)[0]
		item = frappe.get_all(
			"Item", filters={"disabled": 0, "is_sales_item": 1, "has_variants": 0}, pluck="name", limit=1
		)[0]
		result = run_wizard(
			"create_sales_invoice",
			{"customer": customer, "items": [{"item": item, "qty": 2, "rate": 1_500_000}], "vat": 0},
		)
		self.assertFalse(result.get("incomplete"), result)
		name = result["actions"][0]["name"]
		invoice = frappe.get_doc("Sales Invoice", name)
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(invoice.customer, customer)
		self.assertEqual(invoice.items[0].qty, 2)
		self.assertEqual(invoice.items[0].rate, 1_500_000)

	def test_summary(self):
		summary = get_summary()
		keys = {card["key"] for card in summary["cards"]}
		self.assertTrue({"sales", "receivable", "tasks"} <= keys)
