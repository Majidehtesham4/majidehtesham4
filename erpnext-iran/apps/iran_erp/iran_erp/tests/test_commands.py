import datetime

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from iran_erp.commands.engine import _prefer_fitting, _prefer_specific, _without_names, get_matcher, handle
from iran_erp.commands.handlers.general import persian_words
from iran_erp.commands.text import find_date, find_numbers, find_period, stem, to_rial, tokens


class TestText(UnitTestCase):
	def test_numbers(self):
		def first(text):
			return find_numbers(tokens(text))[0].value

		self.assertEqual(first("۱۲ میلیون"), 12_000_000)
		self.assertEqual(first("دو و نیم میلیون"), 2_500_000)
		self.assertEqual(first("سه تا"), 3)
		self.assertEqual(first("۱,۲۰۰,۰۰۰ ریال"), 1_200_000)
		self.assertEqual(first("صد و بیست هزار"), 120_000)
		# "نه" alone is "no", not nine
		self.assertEqual(find_numbers(tokens("نه ممنون")), [])

	def test_toman(self):
		number = find_numbers(tokens("۵۰۰ هزار تومان"))[0]
		self.assertEqual(to_rial(number, "IRR"), 5_000_000)

	def test_dates(self):
		self.assertEqual(find_date(tokens("سررسید ۱۴۰۵/۰۸/۰۱"))[0], datetime.date(2026, 10, 23))
		self.assertEqual(find_date(tokens("۳۰ آبان ۱۴۰۵"))[0], datetime.date(2026, 11, 21))
		self.assertEqual(find_date(tokens("2026-10-23"))[0], datetime.date(2026, 10, 23))
		self.assertIsNotNone(find_date(tokens("فردا"))[0])
		self.assertEqual(find_period(tokens("فروش این ماه"))[1], "این ماه")
		self.assertEqual(find_period(tokens("هزینه‌های ماه گذشته"))[1], "ماه گذشته")

	def test_spelling(self):
		# Arabic letters, half spaces and spoken endings read the same as the written forms
		self.assertEqual(tokens("فاكتورهاي فروش"), tokens("فاکتور‌های فروش"))
		self.assertEqual(stem("مشتریا"), stem("مشتری‌ها".replace("‌", "")))
		self.assertEqual(tokens("پیش‌فاکتور"), tokens("پیش فاکتور"))
		self.assertIn("acc-sinv-2026-00006", tokens("فاکتور ACC-SINV-2026-00006"))

	def test_words(self):
		self.assertEqual(persian_words(12_500_000), "دوازده میلیون و پانصد هزار")
		self.assertEqual(persian_words(1_001), "یک هزار و یک")


class TestMatching(IntegrationTestCase):
	def test_paraphrases(self):
		cases = {
			"امروز چقدر فروختیم": "sales_total",
			"کدوم فاکتورها هنوز پولشون نیومده": "overdue_sales",
			"چقدر پول تو بانک داریم": "cash_position",
			"چک‌هایی که این هفته سررسید میشن": "cheques_due",
			"کالاهایی که داره تموم میشه": "low_stock",
			"امسال سود کردیم یا ضرر": "profit_loss",
			"یه سفارش فروش جدید باز کن": "new_document",
			"ترازنامه رو نشون بده": "open_report",
		}
		matcher = get_matcher()
		for question, expected in cases.items():
			ranked = _prefer_fitting(question, _prefer_specific(matcher.rank(_without_names(question))))
			self.assertEqual(ranked[0][0], expected, question)

	def test_unknown_goes_to_ai(self):
		self.assertTrue(handle("یه چیزی بگو", ai_available=True).get("delegate"))
		self.assertTrue(handle("تحلیل کن چرا فروش کم شده", ai_available=True).get("delegate"))
		self.assertTrue(handle("یه چیزی بگو", ai_available=False).get("unrecognized"))


class TestConversation(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		if not frappe.db.exists("Customer", "مشتری آزمون چت"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "مشتری آزمون چت",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}),
				}
			).insert()
		if not frappe.db.exists("Item", "TEST-CHAT-ITEM"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "TEST-CHAT-ITEM",
					"item_name": "کالای آزمون چت",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}),
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert()
		frappe.cache.delete_keys("iran_cmd_entities")
		frappe.local.iran_cmd_index = {}

	def test_invoice_with_follow_up_questions(self):
		reply = handle("برای مشتری آزمون چت فاکتور بزن")
		self.assertEqual(reply["state"]["waiting"], "items")
		reply = handle("۳ تا کالای آزمون چت به قیمت ۲ میلیون", reply["state"])
		if reply.get("state"):
			# The company has a default VAT template: the invoice asks about it
			self.assertEqual(reply["state"]["waiting"], "vat")
			reply = handle("بدون مالیات", reply["state"])
		invoice = frappe.get_doc("Sales Invoice", reply["actions"][0]["name"])
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(invoice.customer, "مشتری آزمون چت")
		self.assertEqual(
			(invoice.items[0].item_code, invoice.items[0].qty, invoice.items[0].rate),
			("TEST-CHAT-ITEM", 3, 2_000_000),
		)
		self.assertFalse(invoice.taxes)

	def test_balance_and_cancel(self):
		reply = handle("مانده حساب مشتری آزمون چت")
		self.assertEqual(reply["intent"], "balance")
		self.assertIn("مشتری آزمون چت", reply["answer"])
		reply = handle("فاکتور بزن")
		self.assertEqual(reply["state"]["waiting"], "customer")
		self.assertIsNone(handle("لغو", reply["state"])["state"])


class TestBankAndLearning(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		# A ledger account of its own: each one can belong to a single bank account
		ledger = frappe.db.get_value("Account", {"company": company, "account_name": "بانک آزمون چت"})
		if not ledger:
			parent = frappe.db.get_value(
				"Account",
				frappe.db.get_value(
					"Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name"
				),
				"parent_account",
			)
			ledger = (
				frappe.get_doc(
					{
						"doctype": "Account",
						"account_name": "بانک آزمون چت",
						"parent_account": parent,
						"company": company,
						"account_type": "Bank",
					}
				)
				.insert()
				.name
			)
		if not frappe.db.exists("Bank", "بانک آزمون"):
			frappe.get_doc({"doctype": "Bank", "bank_name": "بانک آزمون"}).insert()
		self.bank_account = frappe.db.get_value("Bank Account", {"account_name": "حساب آزمون چت"})
		if not self.bank_account:
			self.bank_account = (
				frappe.get_doc(
					{
						"doctype": "Bank Account",
						"account_name": "حساب آزمون چت",
						"bank": "بانک آزمون",
						"is_company_account": 1,
						"company": company,
						"account": ledger,
					}
				)
				.insert()
				.name
			)
		self.ledger = ledger
		TestConversation.setUp(self)

	def test_payment_into_a_named_bank_account(self):
		reply = handle("مشتری آزمون چت ۵ میلیون به حساب بانک آزمون واریز کرد")
		payment = frappe.get_doc("Payment Entry", reply["actions"][0]["name"])
		self.assertEqual(payment.payment_type, "Receive")
		self.assertEqual((payment.bank_account, payment.paid_to), (self.bank_account, self.ledger))
		self.assertEqual(payment.paid_amount, 5_000_000)

	def test_learned_sentence_is_understood_next_time(self):
		from iran_erp.commands import engine
		from iran_erp.commands.learning import learn

		sentence = "مشتری آزمون چت بابت تسویه حساب ده میلیون پول نقد آورد"
		self.assertTrue(learn("receive_payment", sentence))
		engine._cache.clear()
		ranked = engine.get_matcher().rank(
			engine._without_names("یکی بابت تسویه حساب بیست میلیون پول نقد آورد")
		)
		self.assertEqual(ranked[0][0], "receive_payment")
		# Learning the same wording twice adds nothing
		self.assertFalse(learn("receive_payment", sentence))


class TestJalaliPeriods(UnitTestCase):
	def test_ranges_follow_jalali_months(self):
		from iran_erp.overrides.jalali_periods import jalali_ranges, period_label, range_label

		ranges = jalali_ranges("2026-03-21", "2026-06-21", 1)
		# Farvardin and Ordibehesht have 31 days, so months do not start on the 21st of each month
		self.assertEqual(
			[(str(a), str(b)) for a, b in ranges],
			[("2026-03-21", "2026-04-20"), ("2026-04-21", "2026-05-21"), ("2026-05-22", "2026-06-21")],
		)
		self.assertEqual(period_label(datetime.date(2026, 10, 14), 1), "مهر ۱۴۰۵")
		self.assertEqual(period_label(datetime.date(2026, 10, 14), 3), "پاییز ۱۴۰۵")
		self.assertEqual(range_label("2026-03-21", "2026-06-21"), "فروردین تا خرداد ۱۴۰۵")
		seasons = jalali_ranges("2026-03-21", "2027-03-20", 3)
		self.assertEqual(len(seasons), 4)
		self.assertEqual(str(seasons[-1][1]), "2027-03-20")


class TestExplain(IntegrationTestCase):
	def test_explain_a_page_in_the_chat(self):
		reply = handle("آموزش فاکتور فروش")
		self.assertEqual(reply["intent"], "explain_page")
		self.assertIn("فاکتور فروش سند فروش", reply["answer"])
