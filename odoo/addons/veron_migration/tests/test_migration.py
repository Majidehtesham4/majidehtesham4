"""A company brought into another with its history: the old company is read by SQL like an old database (here the
same one, in the same transaction), and what comes must be what was there once a person confirms it"""

from datetime import date

from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..services.importer import Importer
from ..services.source import Old


@tagged("post_install", "-at_install")
class TestMigration(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
		cls.old_company = cls.env["res.company"].create({"name": "شرکت قدیم", "currency_id": cls.env.ref("base.IRR").id,
			"country_id": cls.env.ref("base.ir").id})
		cls.new_company = cls.env["res.company"].create({"name": "شرکت جدید", "currency_id": cls.env.ref("base.IRR").id,
			"country_id": cls.env.ref("base.ir").id})
		cls.env.user.company_ids |= cls.old_company | cls.new_company
		env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.old_company.ids))
		Account = env["account.account"]
		cls.receivable = Account.create({"code": "121000", "name": "دریافتنی", "account_type": "asset_receivable",
			"reconcile": True})
		income = Account.create({"code": "401000", "name": "فروش", "account_type": "income"})
		bank_account = Account.create({"code": "111200", "name": "بانک", "account_type": "asset_cash"})
		tax_account = Account.create({"code": "211500", "name": "مالیات فروش", "account_type": "liability_current"})
		cls.sale_journal = env["account.journal"].create({"name": "فروش", "code": "OSAL", "type": "sale",
			"default_account_id": income.id})
		cls.bank = env["account.journal"].create({"name": "بانک", "code": "OBNK", "type": "bank",
			"default_account_id": bank_account.id})
		group = env["account.tax.group"].create({"name": "مالیات بر ارزش افزوده", "company_id": cls.old_company.id})
		# Payments go through an outstanding receipts account, as in a company with its chart
		receipts = Account.create({"code": "111300", "name": "دریافت‌های در راه", "account_type": "asset_current",
			"reconcile": True})
		cls.bank.inbound_payment_method_line_ids.payment_account_id = receipts
		tax = env["account.tax"].create({"name": "مالیات ۱۰٪ آزمایشی", "amount": 10, "type_tax_use": "sale",
			"company_id": cls.old_company.id, "tax_group_id": group.id})
		tax.repartition_line_ids.filtered(lambda l: l.repartition_type == "tax").account_id = tax_account
		cls.customer = env["res.partner"].create({"name": "مشتری انتقالی", "company_id": cls.old_company.id,
			"property_account_receivable_id": cls.receivable.id})
		cls.product = env["product.product"].create({"name": "کالای انتقالی", "list_price": 1000000,
			"company_id": cls.old_company.id})
		cls.invoice = env["account.move"].create({"move_type": "out_invoice", "partner_id": cls.customer.id,
			"journal_id": cls.sale_journal.id, "invoice_date": date(2025, 1, 10), "invoice_line_ids": [Command.create({
			"product_id": cls.product.id, "quantity": 3, "price_unit": 1000000, "account_id": income.id,
			"tax_ids": [Command.set(tax.ids)]})]})
		cls.invoice.action_post()
		env["account.payment.register"].with_context(active_model="account.move", active_ids=cls.invoice.ids).create({
			"amount": 1000000, "payment_date": date(2025, 2, 1), "journal_id": cls.bank.id})._create_payments()
		cls.env.flush_all()

	def test_company_brought_and_confirmed(self):
		env = self.env(context=dict(self.env.context, allowed_company_ids=self.new_company.ids))
		self.assertEqual(env.company, self.new_company)
		old = Old(self.env.cr)
		work = Importer(env, old, None, "18.0", self.old_company.id, say=lambda *a: None)
		for step in work.steps():
			step()
			work.flush()
			env.flush_all()
		self.assertEqual(self.new_company.name, "شرکت جدید", "two companies here cannot have one name")
		self.assertIn("Another company here is named «شرکت قدیم»; this one keeps its name.", work.notes)
		invoice = env["account.move"].browse(work.map["account.move"][self.invoice.id])
		self.assertEqual((invoice.state, invoice.name, invoice.company_id), ("draft", self.invoice.name, self.new_company),
			"brought as a draft with its old number")
		self.assertEqual(invoice.amount_total, 3300000)
		self.assertNotEqual(invoice.partner_id, self.customer, "a contact of the old company is a contact here")
		self.assertEqual(invoice.partner_id.name, "مشتری انتقالی")
		self.assertEqual(invoice.line_ids.account_id.mapped("code").count("121000"), 1)

		migration = env["veron.migration"].with_context(migration_old_cursor=self.env.cr, lang="en_US")._record(work, "18.0",
			self.env.cr.dbname)
		self.assertEqual(migration.moves_to_post, 2, "the invoice and its payment")
		migration.action_compare()
		self.assertIn("same balance", migration.comparison_html)
		migration.action_confirm()
		while not migration._confirm_step(100):
			pass
		self.assertFalse(migration.failures, migration.failures)
		self.assertEqual((invoice.state, invoice.name), ("posted", self.invoice.name), "posted with its old number")
		self.assertEqual((invoice.payment_state, invoice.amount_residual), (self.invoice.payment_state,
			self.invoice.amount_residual), "paid in part, as it was")
		payment = env["account.payment"].search([("company_id", "=", self.new_company.id)])
		self.assertTrue(payment, (dict(work.failed), work.notes))
		self.assertEqual((payment.amount, payment.state), (1000000, "in_process" if payment.state == "in_process" else
			"paid"))
		self.assertTrue(payment.is_reconciled)
		self.assertIn("same balance", migration.comparison_html)

		# A second run brings nothing twice (here the records made by the first run are in the same database, so
		# only what belongs to the old company is looked at)
		again = Importer(env, old, None, "18.0", self.old_company.id, say=lambda *a: None)
		for step in again.steps():
			step()
		for name in ("journal entries", "payments", "account.account", "account.tax", "account.journal"):
			self.assertFalse(again.counts.get(name), name)
