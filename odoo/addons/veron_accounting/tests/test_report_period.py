from odoo import fields
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReportPeriod(TransactionCase):
	def test_reports_open_on_the_fiscal_year(self):
		"""the trial balance, the journal ledger and the VAT report open on this fiscal year, to today"""
		today = fields.Date.context_today(self.env.user)
		start = self.env.company.compute_fiscalyear_dates(today)["date_from"]
		for model in ("trial.balance.report.wizard", "journal.ledger.report.wizard", "vat.report.wizard"):
			values = self.env[model].default_get(["date_from", "date_to"])
			self.assertEqual((values["date_from"], values["date_to"]), (start, today), model)
		wizard = self.env["trial.balance.report.wizard"].create({})
		self.assertEqual(wizard.date_from, start, "a trial balance can be made at once")

	def test_trial_balance_form_keeps_its_period(self):
		"""opened as a person opens it (its onchanges run), the trial balance still has its period"""
		today = fields.Date.context_today(self.env.user)
		start = self.env.company.compute_fiscalyear_dates(today)["date_from"]
		for model in ("trial.balance.report.wizard", "journal.ledger.report.wizard", "vat.report.wizard"):
			form = Form(self.env[model])
			self.assertEqual((form.date_from, form.date_to), (start, today), model)
