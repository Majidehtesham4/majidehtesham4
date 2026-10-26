from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCheque(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = cls.env.company
		cls.company._veron_cheque_setup()
		cls.bank = cls.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1)
		cls.customer = cls.env["res.partner"].create({"name": "مشتری چک"})
		cls.vendor = cls.env["res.partner"].create({"name": "تأمین‌کننده چک"})
		cls.Cheque = cls.env["veron.cheque"]

	def balance(self, account, partner=None):
		domain = [("account_id", "=", account.id), ("parent_state", "=", "posted")]
		if partner:
			domain.append(("partner_id", "=", partner.id))
		return sum(self.env["account.move.line"].search(domain).mapped("balance"))

	def received(self, sayad="1234567890123456"):
		return self.Cheque.create({"direction": "in", "partner_id": self.customer.id, "amount": 50000000,
			"serial": "778899", "sayad_id": sayad, "due_date": "2026-12-01", "bank_journal_id": self.bank.id})

	def test_accounts_from_the_iranian_chart(self):
		self.assertEqual(self.company.veron_cheque_hand_account_id.code, "111203")
		self.assertEqual(self.company.veron_cheque_payable_account_id.code, "211101")
		self.assertTrue(self.company.veron_cheque_journal_id)

	def test_received_cashed(self):
		cheque = self.received()
		hand = self.company.veron_cheque_hand_account_id
		collection = self.company.veron_cheque_collection_account_id
		receivable = self.customer.property_account_receivable_id
		cheque.action_receive()
		self.assertEqual(self.balance(hand, self.customer), 50000000)
		self.assertEqual(self.balance(receivable, self.customer), -50000000)
		cheque.action_deposit()
		self.assertEqual(self.balance(hand, self.customer), 0)
		self.assertEqual(self.balance(collection, self.customer), 50000000)
		cheque.action_cash()
		self.assertEqual(cheque.state, "cashed")
		self.assertEqual(self.balance(collection, self.customer), 0)
		self.assertEqual(len(cheque.move_ids), 3)
		self.assertTrue(all(m.state == "posted" for m in cheque.move_ids))
		# The two lines on the cheques-in-hand account are matched
		self.assertTrue(all(cheque.move_ids.line_ids.filtered(lambda l: l.account_id == hand).mapped("reconciled")))
		self.assertTrue(cheque.amount_words)

	def test_bounced_then_returned(self):
		cheque = self.received()
		cheque.action_receive()
		cheque.action_deposit()
		cheque.action_bounce()
		bounced = self.company.veron_cheque_bounced_account_id
		self.assertEqual(self.balance(bounced, self.customer), 50000000)
		cheque.action_return()
		self.assertEqual(self.balance(bounced, self.customer), 0)
		self.assertEqual(self.balance(self.customer.property_account_receivable_id, self.customer), 0)
		with self.assertRaises(UserError):
			cheque.action_cash()

	def test_endorsed(self):
		cheque = self.received()
		cheque.action_receive()
		with self.assertRaises(UserError):
			cheque.action_endorse()
		cheque.endorse_partner_id = self.vendor
		cheque.action_endorse()
		self.assertEqual(self.balance(self.vendor.property_account_payable_id, self.vendor), 50000000)
		self.assertEqual(self.balance(self.company.veron_cheque_hand_account_id, self.customer), 0)

	def test_issued(self):
		book = self.env["veron.cheque.book"].create({"name": "دسته چک", "journal_id": self.bank.id, "first_serial": 500100, "sheets": 10})
		cheque = self.Cheque.create({"direction": "out", "partner_id": self.vendor.id, "amount": 20000000, "book_id": book.id,
			"serial": str(book.next_serial), "due_date": "2026-12-10", "bank_journal_id": self.bank.id})
		self.assertEqual(book.next_serial, 500101)
		payable = self.company.veron_cheque_payable_account_id
		cheque.action_issue()
		self.assertEqual(self.balance(payable, self.vendor), -20000000)
		cheque.action_cash()
		self.assertEqual(self.balance(payable, self.vendor), 0)
		other = self.Cheque.create({"direction": "out", "partner_id": self.vendor.id, "amount": 1000, "book_id": book.id,
			"serial": str(book.next_serial), "due_date": "2026-12-10", "bank_journal_id": self.bank.id})
		other.action_issue()
		other.action_cancel()
		# Only the cashed cheque paid the vendor; the cancelled one nets out
		self.assertEqual(self.balance(self.vendor.property_account_payable_id, self.vendor), 20000000)
		self.assertEqual(self.balance(payable, self.vendor), 0)
		self.assertEqual(other.state, "cancelled")

	def test_checks(self):
		with self.assertRaises(ValidationError):
			self.received(sayad="12345")
		cheque = self.received()
		cheque.action_receive()
		with self.assertRaises(UserError):
			cheque.unlink()
