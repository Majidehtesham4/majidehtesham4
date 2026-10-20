"""The assistant's evaluation set (commands/evaluation.py) on data made for it, and the figures,
drafts and links behind the answers."""

import json

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
		self._cars()
		for kind in ("customer", "investor", "user", "party"):
			if kind in entities.SOURCES:
				entities.forget(kind)

	def _cars(self):
		"""A black KMC K7 of 1401 in the lot, and one car that came in long before the others."""
		from frappe.utils import add_days

		if not frappe.db.exists("Iran Car Color", "مشکی"):
			frappe.get_doc({"doctype": "Iran Car Color", "color_name": "مشکی"}).insert()
		model = frappe.db.get_value("Iran Car Model", {"brand": "کی ام سی", "model": "K7"})
		if not model:
			model = frappe.get_doc({"doctype": "Iran Car Model", "brand": "کی ام سی", "model": "K7", "made_in": "Made in Iran"}).insert().name
		car = {"doctype": "Iran Vehicle", "company": self.company, "status": "Ready for Sale"}
		if not frappe.db.exists("Iran Vehicle", {"car_model": model, "color": "مشکی", "year": "1401"}):
			frappe.get_doc({**car, "car_model": model, "year": "1401", "color": "مشکی", "entry_date": nowdate()}).insert()
		self.old_car = frappe.get_doc({**car, "car_model": model, "year": "1399", "entry_date": add_days(nowdate(), -400)}).insert().name

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

	def test_answers_keep_to_what_was_asked(self):
		from iran_erp.commands.engine import handle

		# The oldest car: that one, not the stock list
		reply = handle("قدیمی‌ترین ماشین که پذیرش شده کدومه؟")
		self.assertEqual(reply["intent"], "car_aging")
		self.assertEqual(reply["trace"]["records"], 1)
		self.assertIn(self.old_car, reply["answer"])
		self.assertIn("Vehicles%20in%20Stock", reply["actions"][0]["url"])
		# Longest first, a few of them
		reply = handle("کدوم ماشین‌ها بیشترین زمان رو تو پارکینگ موندن؟")
		self.assertLessEqual(reply["trace"]["records"], 10)
		self.assertLess(reply["answer"].index(self.old_car), 400)
		# A sold car is found, and said to be sold
		frappe.db.set_value("Iran Vehicle", self.old_car, {"status": "Sold", "exit_date": nowdate(), "color": "مشکی"})
		reply = handle("ماشین کی ام سی K7 ۱۳۹۹ مشکی رو چک کن فروخته شده؟")
		self.assertEqual((reply["intent"], reply["trace"]["records"]), ("car_search", 1))
		self.assertIn("فروخته شده: بله", reply["answer"])
		self.assertTrue(reply["actions"][0]["url"].endswith(self.old_car))
		# Not on record: said, with the details
		reply = handle("ماشین کی ام سی K7 ۱۴۰۰ سفید فروخته شده؟")
		self.assertEqual(reply["trace"]["records"], 0)
		self.assertIn("پیدا نشد", reply["answer"])
		# Sales by branch, with the period said
		reply = handle("یک گزارش از فروش هر شعبه بده")
		self.assertEqual(reply["intent"], "sales_by_branch")
		self.assertIn("امسال", reply["answer"])
		# No subject: a question about the subject, nothing run
		reply = handle("یک گزارش بهم بده")
		self.assertEqual(reply["state"]["waiting"], "area")
		self.assertNotIn("create_user_login", json.dumps(reply["state"]))
		# «خانم کریمی» is not «آقای کریمی», and not every «خانم»
		reply = handle("خانم کریمی چقدر بدهکار یا بستانکاره؟")
		self.assertEqual([label for _v, label in reply["state"]["options"]], ["آقای کریمی"])
