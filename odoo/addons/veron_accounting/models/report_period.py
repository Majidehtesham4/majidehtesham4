from odoo import api, fields, models


def _period(record, fields_list, values):
	"""The report's period, when none is given: the company's fiscal year, from its first day to today"""
	today = fields.Date.context_today(record)
	start = record.env.company.compute_fiscalyear_dates(today)["date_from"]
	if "date_from" in fields_list and not values.get("date_from"):
		values["date_from"] = start
	if "date_to" in fields_list and not values.get("date_to"):
		values["date_to"] = today
	return values


class TrialBalanceWizard(models.TransientModel):
	"""OCA's trial balance opened with no period (its date range, empty, also emptied the dates), so it could
	not be shown before two dates were chosen"""
	_inherit = "trial.balance.report.wizard"

	@api.model
	def default_get(self, fields_list):
		return _period(self, fields_list, super().default_get(fields_list))

	@api.onchange("date_range_id")
	def onchange_date_range_id(self):
		# the dates of a range, when one is chosen; none chosen, the dates stay
		if self.date_range_id:
			super().onchange_date_range_id()


class JournalLedgerWizard(models.TransientModel):
	_inherit = "journal.ledger.report.wizard"

	@api.model
	def default_get(self, fields_list):
		return _period(self, fields_list, super().default_get(fields_list))

	@api.onchange("date_range_id")
	def onchange_date_range_id(self):
		if self.date_range_id:
			super().onchange_date_range_id()


class VatReportWizard(models.TransientModel):
	_inherit = "vat.report.wizard"

	@api.model
	def default_get(self, fields_list):
		return _period(self, fields_list, super().default_get(fields_list))

	@api.onchange("date_range_id")
	def onchange_date_range_id(self):
		if self.date_range_id:
			super().onchange_date_range_id()
