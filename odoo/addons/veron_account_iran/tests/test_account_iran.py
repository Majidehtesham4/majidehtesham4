from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.veron_core.models import jalali


@tagged("post_install", "-at_install")
class TestAccountIran(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = cls.env.company
		cls.Account = cls.env["account.account"]
		cls.journal = cls.env["account.journal"].search([("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1)
		cls.purchase = cls.env["account.journal"].search([("type", "=", "purchase"), ("company_id", "=", cls.company.id)], limit=1)
		cls.cash = cls.account("111001")
		cls.expense = cls.Account.search([("account_type", "=", "expense"), ("company_ids", "in", cls.company.id)], limit=1)
		cls.vendor = cls.env["res.partner"].create({"name": "پیمانکار نمونه", "vat": "411111111111"})
		cls.env["account.tax"]._veron_retentions(cls.company)

	@classmethod
	def account(cls, code):
		return cls.Account.search([("code", "=", code), ("company_ids", "in", cls.company.id)], limit=1)

	def entry(self, date, amount=1000.0, post=True, ref="آزمایشی", kind="normal"):
		move = self.env["account.move"].create({"move_type": "entry", "journal_id": self.journal.id, "date": date, "ref": ref,
			"veron_voucher_kind": kind, "line_ids": [
				(0, 0, {"account_id": self.expense.id, "debit": amount, "name": "هزینه"}),
				(0, 0, {"account_id": self.cash.id, "credit": amount, "name": "صندوق"})]})
		if post:
			move.action_post()
		return move

	# --- voucher numbers

	def test_voucher_numbers_by_shamsi_year(self):
		year = jalali.to_jalali(jalali.to_gregorian(1404, 6, 1))[0]
		later = self.entry(jalali.to_gregorian(1404, 6, 10))
		earlier = self.entry(jalali.to_gregorian(1404, 2, 5))
		next_year = self.entry(jalali.to_gregorian(1405, 1, 15))
		first = self.env["account.move"].search([("veron_voucher_year", "=", 1404), ("company_id", "=", self.company.id)],
			order="veron_voucher_number")
		self.assertEqual(later.veron_voucher_year, year)
		self.assertEqual(earlier.veron_voucher_number, later.veron_voucher_number + 1, "given in the order of posting")
		self.assertEqual((next_year.veron_voucher_year, next_year.veron_voucher_number),
			(1405, len(self.env["account.move"].search([("veron_voucher_year", "=", 1405)]))))
		opening = self.entry(jalali.to_gregorian(1404, 12, 29), kind="opening")
		count = self.env["account.move"]._veron_renumber(self.company, 1404)
		self.assertGreaterEqual(count, len(first) + 1, "every posted voucher of the year, those posted before the module too")
		self.assertEqual(opening.veron_voucher_number, 1, "the opening voucher first")
		self.assertLess(earlier.veron_voucher_number, later.veron_voucher_number, "then in the order of the dates")
		self.assertEqual(later.veron_voucher, f"1404-{later.veron_voucher_number}")

	def test_two_posted_at_once(self):
		moves = self.entry("2026-10-01", post=False) | self.entry("2026-10-02", post=False)
		moves.action_post()
		self.assertEqual(len(set(moves.mapped("veron_voucher_number"))), 2, "never the same number twice")

	def test_a_locked_year_is_not_renumbered(self):
		self.entry(jalali.to_gregorian(1403, 5, 1))
		self.company.fiscalyear_lock_date = jalali.to_gregorian(1403, 12, 29)
		with self.assertRaises(UserError):
			self.env["account.move"]._veron_renumber(self.company, 1403)

	# --- templates and aggregation

	def test_voucher_template(self):
		Template = self.env["veron.voucher.template"]
		with self.assertRaises(ValidationError):
			Template.create({"name": "نادرست", "journal_id": self.journal.id, "line_ids": [
				(0, 0, {"side": "debit", "account_id": self.expense.id, "share": 60}),
				(0, 0, {"side": "credit", "account_id": self.cash.id, "share": 100})]})
		rent = Template.create({"name": "اجاره", "journal_id": self.journal.id, "line_ids": [
			(0, 0, {"side": "debit", "account_id": self.expense.id, "share": 33.33}),
			(0, 0, {"side": "debit", "account_id": self.expense.id, "share": 66.67}),
			(0, 0, {"side": "credit", "account_id": self.cash.id, "share": 100})]})
		move = rent._make(1000.0, "2026-10-01")
		self.assertEqual(move.state, "draft")
		self.assertEqual(sum(move.line_ids.mapped("debit")), 1000.0)
		self.assertEqual(sorted(move.line_ids.mapped("debit")), [0.0, 333.0, 667.0], "rounded in rial, the rest on the last")

	def test_aggregate_drafts_only(self):
		drafts = self.entry("2026-10-01", 100, post=False) | self.entry("2026-10-02", 250, post=False)
		wizard = self.env["veron.aggregate.vouchers"].with_context(active_ids=drafts.ids).create({})
		action = wizard.action_aggregate()
		merged = self.env["account.move"].browse(action["res_id"])
		self.assertFalse(drafts.exists(), "the drafts are replaced by the aggregated voucher")
		self.assertEqual(len(merged.line_ids), 2)
		self.assertEqual(merged.line_ids.filtered(lambda l: l.account_id == self.expense).debit, 350)
		self.assertIn("آزمایشی", merged.veron_aggregated_from)
		posted = self.entry("2026-10-03") | self.entry("2026-10-04", post=False)
		with self.assertRaises(UserError):
			self.env["veron.aggregate.vouchers"].with_context(active_ids=posted.ids).create({}).action_aggregate()

	# --- deposits held

	def test_insurance_deposit_and_release(self):
		deposit = self.env["account.tax"].search([("name", "=", "سپرده بیمه ۵٪"), ("company_id", "=", self.company.id)])
		self.assertTrue(deposit, "made for a company on the Iranian chart")
		self.assertFalse(self.env["account.tax"]._veron_retentions(self.company), "made once")
		bill = self.env["account.move"].create({"move_type": "in_invoice", "partner_id": self.vendor.id,
			"invoice_date": "2026-10-05", "journal_id": self.purchase.id, "invoice_line_ids": [(0, 0, {
				"name": "پیمان ساخت", "quantity": 1, "price_unit": 100_000_000, "account_id": self.expense.id,
				"tax_ids": [(6, 0, deposit.ids)]})]})
		bill.action_post()
		self.assertEqual(bill.amount_total, 95_000_000, "the vendor is owed the amount less the deposit")
		held = bill.line_ids.filtered(lambda l: l.account_id == self.account("211205"))
		self.assertEqual((held.credit, held.partner_id), (5_000_000, self.vendor))
		wizard = self.env["veron.release.deposit"].create({"partner_id": self.vendor.id, "account_id": self.account("211205").id,
			"amount": 1})
		self.assertEqual(wizard.held, 5_000_000)
		wizard.amount = 6_000_000
		with self.assertRaises(UserError):
			wizard.action_release()
		wizard.amount = 5_000_000
		move = self.env["account.move"].browse(wizard.action_release()["res_id"])
		self.assertEqual(move.state, "draft", "a person posts it")
		move.action_post()
		self.assertEqual(self.env["veron.release.deposit"].create({"partner_id": self.vendor.id,
			"account_id": self.account("211205").id, "amount": 1}).held, 0)

	# --- books and printed forms

	def test_books(self):
		self.entry("2026-09-25", 400)
		self.entry("2026-10-05", 600)
		Books = self.env["veron.account.iran.books"]
		trial = Books.trial_balance(self.company, "2026-10-01", "2026-10-31", "ledger")
		self.assertEqual(round(sum(r["debit"] for r in trial), 2), round(sum(r["credit"] for r in trial), 2))
		cash = next(r for r in trial if r["code"] == "1110")
		self.assertGreaterEqual(cash["balance_credit"] - cash["balance_debit"], 1000, "the balance includes before the period")
		self.assertEqual({len(r["code"]) for r in Books.trial_balance(self.company, "2026-10-01", "2026-10-31", "group")}, {2})
		journal = Books.journal_book(self.company, "2026-10-01", "2026-10-31")
		self.assertTrue(any(r["debit"] == 600 for v in journal for r in v["rows"]))
		ledger = Books.general_ledger(self.company, "2026-10-01", "2026-10-31", {"1110"})
		self.assertEqual(ledger[0]["rows"][-1]["side"], "بس")

	def test_printed_forms(self):
		move = self.entry("2026-10-05", 1_500_000)
		html = self.env["ir.actions.report"]._render_qweb_html("veron_account_iran.report_voucher", move.ids)[0].decode()
		self.assertIn("سند حسابداری", html)
		self.assertIn(move.veron_voucher, html)
		customer = self.env["res.partner"].create({"name": "خریدار نمونه", "vat": "10101010101", "zip": "1234567890"})
		product = self.env["product.product"].create({"name": "کالای نمونه", "list_price": 2_000_000, "default_code": "K-1"})
		invoice = self.env["account.move"].create({"move_type": "out_invoice", "partner_id": customer.id,
			"invoice_date": "2026-10-05", "invoice_line_ids": [(0, 0, {"product_id": product.id, "quantity": 3,
				"price_unit": 2_000_000, "discount": 10, "tax_ids": [(6, 0, [])]})]})
		html = self.env["ir.actions.report"]._render_qweb_html("veron_account_iran.report_official_invoice", invoice.ids)[0].decode()
		self.assertIn("پیش‌فاکتور", html, "a draft is a proforma")
		for text in ("مشخصات فروشنده", "1234567890", "6,000,000", "600,000", "5,400,000"):
			self.assertIn(text, html)
		invoice.action_post()
		html = self.env["ir.actions.report"]._render_qweb_html("veron_account_iran.report_official_invoice", invoice.ids)[0].decode()
		self.assertIn("صورتحساب فروش کالا و خدمات", html)
		for book in ("trial", "journal", "ledger"):
			wizard = self.env["veron.books.wizard"].create({"book": book, "date_from": "2026-10-01", "date_to": "2026-10-31"})
			html = self.env["ir.actions.report"]._render_qweb_html("veron_account_iran.report_books", wizard.ids)[0].decode()
			self.assertIn({"trial": "تراز آزمایشی", "journal": "دفتر روزنامه", "ledger": "دفتر کل"}[book], html)
		treasury = self.env["veron.treasury.wizard"].create({"date_from": "2026-10-01", "date_to": "2026-10-31"})
		html = self.env["ir.actions.report"]._render_qweb_html("veron_account_iran.report_treasury", treasury.ids)[0].decode()
		self.assertIn("صندوق و بانک", html)
