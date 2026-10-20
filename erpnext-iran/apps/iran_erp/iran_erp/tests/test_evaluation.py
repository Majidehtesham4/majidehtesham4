"""The assistant's evaluation set (commands/evaluation.py) on data made for it, and the figures,
drafts and links behind the answers."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from iran_erp.commands import entities
from iran_erp.commands.capabilities import CAPABILITIES, catalog, find_capability, run_capability
from iran_erp.commands.engine import INTENT_BY_NAME, handle
from iran_erp.commands.evaluation import CASES, evaluate, run_case


class TestEvaluation(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.lang = "fa"
		self.company = frappe.defaults.get_global_default("company")
		if not frappe.db.exists("Iran Investor", {"full_name": "مجید احتشام"}):
			frappe.get_doc({"doctype": "Iran Investor", "full_name": "مجید احتشام", "mobile": "09121112233"}).insert()
		customer = frappe.db.get_value("Customer", {"customer_name": "آقای کریمی"})
		if not customer:
			customer = (
				frappe.get_doc(
					{
						"doctype": "Customer",
						"customer_name": "آقای کریمی",
						"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
						"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
					}
				)
				.insert()
				.name
			)
		self.customer = customer
		# Money paid in advance: in the company's books the customer is in credit (we owe him)
		from erpnext.accounts.party import get_party_account

		cash = frappe.get_cached_value("Company", self.company, "default_cash_account") or frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Cash", "is_group": 0}
		)
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": nowdate(),
				"accounts": [
					{"account": cash, "debit_in_account_currency": 5_000_000},
					{
						"account": get_party_account("Customer", customer, self.company),
						"party_type": "Customer",
						"party": customer,
						"credit_in_account_currency": 5_000_000,
					},
				],
			}
		).insert()
		entry.submit()
		for kind in ("customer", "investor", "user", "party"):
			if kind in entities.SOURCES:
				entities.forget(kind)

	def tearDown(self):
		frappe.db.rollback()

	def test_every_phrasing_reaches_its_capability(self):
		for ai_available in (False, True):
			result = evaluate(ai_available)
			failed = [f"{r['capability']}: {' | '.join(r['turns'])} → {r['why']}" for r in result["results"] if not r["passed"]]
			self.assertFalse(failed, "\n".join(failed))
		self.assertGreaterEqual(sum(len(c["phrasings"]) for c in CASES), 30)

	def test_figures_and_drafts(self):
		# The investor's real record, not a login or an invoice
		reply = run_case(["یک سرمایه‌گذار داریم به نام مجید احتشام، اطلاعاتشو بیار"])
		self.assertIn("09121112233", reply["answer"])
		# The balance with the company's point of view
		reply = run_case(["آقای کریمی چقدر بستانکار است؟"])
		self.assertIn("بستانکار", reply["answer"])
		self.assertIn("۵٬۰۰۰٬۰۰۰", reply["answer"])
		# A login from the chat is a draft: switched off, the password not repeated
		reply = run_case(["یک کاربر حسابدار بساز به اسم سارا نیکو نام کاربری sara.test رمز Sara-12345"])
		user = frappe.db.get_value("User", {"username": "sara.test"}, ["name", "enabled"], as_dict=True)
		self.assertEqual(user.enabled, 0)
		self.assertNotIn("Sara-12345", reply["answer"])
		# A password change waits for yes
		reply = handle("رمز کاربر sara.test رو عوض کن", None)
		reply = handle("Other-99999", reply["state"])
		self.assertTrue(reply["state"].get("confirm"))

	def test_catalog_and_ai_bridge(self):
		names = {c["id"] for c in catalog()}
		for name in CAPABILITIES:
			self.assertIn(name, INTENT_BY_NAME)
			self.assertIn(name, names)
		found = find_capability("یک سرمایه‌گذار داریم به نام مجید احتشام، اطلاعاتشو بیار")
		self.assertEqual(found["capabilities"][0]["id"], "investor_info")
		out = run_capability("balance", "", {"party": "آقای کریمی"})
		self.assertIn("کریمی", out["answer"])
		self.assertTrue(any("General%20Ledger" in link["url"] for link in out["links"]))
		out = run_capability("party_statement", "", {"party": "همه"})
		self.assertTrue(any("Customer%20Ledger%20Summary" in link["url"] for link in out["links"]))
		out = run_capability("set_user_password", "", {"user": "Administrator", "password": "Whatever-123"})
		self.assertIn("needs_confirmation", out)
