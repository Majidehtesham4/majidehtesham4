# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

from unittest import TestCase

import frappe
from frappe.utils import add_days, flt, nowdate

from iran_erp.accounts.chart import CHART_NAME

COMPANY = "Cheque Test Co"
ABBR = "CTC"
AMOUNT = 50_000_000


def account(number):
	return frappe.db.get_value("Account", {"company": COMPANY, "account_number": number})


def balance(number):
	return flt(
		frappe.db.sql(
			"select sum(debit - credit) from `tabGL Entry` where account=%s and is_cancelled=0",
			account(number),
		)[0][0]
	)


# A plain TestCase: Frappe's test records would add a Gregorian fiscal year that clashes with a Jalali one
class TestIranCheque(TestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()

	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Company", COMPANY):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY,
					"abbr": ABBR,
					"default_currency": "IRR",
					"country": "Iran",
					"chart_of_accounts": CHART_NAME,
				}
			).insert()
		for doctype, name, extra in (
			("Customer", "Cheque Test Customer", {"customer_name": "Cheque Test Customer"}),
			("Supplier", "Cheque Test Supplier", {"supplier_name": "Cheque Test Supplier"}),
		):
			if not frappe.db.exists(doctype, name):
				frappe.get_doc({"doctype": doctype, **extra}).insert()

	def make_cheque(self, cheque_type="Received", **kwargs):
		party_type = "Customer" if cheque_type == "Received" else "Supplier"
		cheque = frappe.get_doc(
			{
				"doctype": "Iran Cheque",
				"cheque_type": cheque_type,
				"company": COMPANY,
				"party_type": party_type,
				"party": f"Cheque Test {party_type}",
				"cheque_number": "۱۲۳۴۵۶",
				"sayad_id": "1234567890123456",
				"amount": AMOUNT,
				"posting_date": nowdate(),
				"due_date": add_days(nowdate(), 30),
				"bank_account": account("110301") if cheque_type == "Issued" else None,
				**kwargs,
			}
		).insert()
		cheque.submit()
		return cheque

	def test_receive_deposit_clear(self):
		before = {n: balance(n) for n in ("1302", "1303", "110301")}
		cheque = self.make_cheque()
		self.assertEqual(cheque.status, "In Hand")
		self.assertEqual(cheque.cheque_number, "123456")
		self.assertEqual(balance("1302") - before["1302"], AMOUNT)

		cheque.take_action("deposit", bank_account=account("110301"))
		self.assertEqual(cheque.status, "Deposited")
		self.assertEqual(balance("1302") - before["1302"], 0)
		self.assertEqual(balance("1303") - before["1303"], AMOUNT)

		cheque.take_action("clear")
		cheque.reload()
		self.assertEqual(cheque.status, "Cleared")
		self.assertEqual(balance("1303") - before["1303"], 0)
		self.assertEqual(balance("110301") - before["110301"], AMOUNT)
		self.assertEqual([row.to_status for row in cheque.history], ["In Hand", "Deposited", "Cleared"])

		# Nothing is left to do with a cleared cheque
		self.assertRaises(frappe.ValidationError, cheque.take_action, "bounce")

		cheque.cancel()
		self.assertEqual(cheque.status, "Cancelled")
		for row in cheque.history:
			self.assertEqual(frappe.db.get_value("Journal Entry", row.journal_entry, "docstatus"), 2)
		self.assertEqual(balance("110301"), before["110301"])

	def test_bounce_puts_the_amount_back_on_the_customer(self):
		receivable = account("1301")
		cheque = self.make_cheque()
		cheque.take_action("bounce")
		self.assertEqual(cheque.status, "Bounced")
		entries = frappe.get_all(
			"Journal Entry Account",
			filters={"parent": cheque.history[-1].journal_entry, "account": receivable},
			fields=["party", "debit"],
		)
		self.assertEqual(entries[0].party, "Cheque Test Customer")
		self.assertEqual(entries[0].debit, AMOUNT)

	def test_endorse_to_supplier(self):
		cheque = self.make_cheque()
		self.assertRaises(frappe.ValidationError, cheque.take_action, "endorse")
		cheque.take_action("endorse", endorsed_to_type="Supplier", endorsed_to="Cheque Test Supplier")
		self.assertEqual(cheque.status, "Endorsed")
		self.assertEqual(cheque.endorsed_to, "Cheque Test Supplier")

	def test_issued_cheque(self):
		before = balance("110301")
		cheque = self.make_cheque("Issued")
		self.assertEqual(cheque.status, "Issued")
		self.assertEqual(cheque.cheque_account, account("3102"))
		# Received-only action
		self.assertRaises(frappe.ValidationError, cheque.take_action, "deposit")
		cheque.take_action("clear")
		self.assertEqual(cheque.status, "Cleared")
		self.assertEqual(balance("110301") - before, -AMOUNT)

		bounced = self.make_cheque("Issued")
		bounced.take_action("bounce")
		self.assertEqual(bounced.status, "Bounced")

	def test_cheque_against_invoice_settles_it(self):
		item = frappe.db.get_value("Item", {"item_code": "Cheque Test Service"}) or (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "Cheque Test Service",
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			)
			.insert()
			.name
		)
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": "Cheque Test Customer",
				"currency": "IRR",
				"debit_to": account("1301"),
				"items": [
					{
						"item_code": item,
						"qty": 1,
						"rate": AMOUNT,
						"income_account": account("6102"),
						"cost_center": f"Main - {ABBR}",
					}
				],
			}
		).insert()
		invoice.submit()
		self.make_cheque(against_doctype="Sales Invoice", against_invoice=invoice.name)
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount"), 0)

	def test_validation(self):
		self.assertRaises(frappe.ValidationError, self.make_cheque, sayad_id="123")
		self.assertRaises(frappe.ValidationError, self.make_cheque, amount=0)
		self.assertRaises(frappe.ValidationError, self.make_cheque, "Issued", bank_account=None)
