from odoo import fields, models

from odoo.addons.veron_core.models import jalali


def _year_start(record):
	return jalali.to_gregorian(jalali.to_jalali(fields.Date.context_today(record))[0], 1, 1)


class BooksWizard(models.TransientModel):
	_name = "veron.books.wizard"
	_description = "Legal Books"

	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	book = fields.Selection([("trial", "Four-Column Trial Balance"), ("journal", "Journal Book"),
		("ledger", "General Ledger Book")], required=True, default="trial")
	level = fields.Selection([("group", "Group"), ("ledger", "Ledger"), ("account", "Sub-Ledger")], default="ledger",
		required=True)
	date_from = fields.Date(required=True, default=_year_start)
	date_to = fields.Date(required=True, default=fields.Date.context_today)
	ledger_codes = fields.Char("Ledger Codes", help="For the general ledger: codes of four digits separated by commas; "
		"empty for all")

	def _data(self):
		self.ensure_one()
		Books = self.env["veron.account.iran.books"]
		if self.book == "trial":
			return Books.trial_balance(self.company_id, self.date_from, self.date_to, self.level)
		if self.book == "journal":
			return Books.journal_book(self.company_id, self.date_from, self.date_to)
		codes = {code.strip() for code in (self.ledger_codes or "").replace("،", ",").split(",") if code.strip()}
		return Books.general_ledger(self.company_id, self.date_from, self.date_to, codes or None)

	def _period(self):
		from ..models.account_move import shamsi

		return f"{shamsi(self.date_from)} - {shamsi(self.date_to)}"

	def action_print(self):
		return self.env.ref("veron_account_iran.action_report_books").report_action(self)
