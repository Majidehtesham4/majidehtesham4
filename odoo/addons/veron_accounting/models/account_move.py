import datetime

from odoo import fields, models

from odoo.addons.veron_core.models import jalali


class AccountMove(models.Model):
	"""Numbers of entries and invoices of a company in Iran in the Shamsi year: «INV/1405/00001»,
	restarting at Nowruz, a monthly series by Shamsi month."""

	_inherit = "account.move"

	# Odoo reads a year in a number only from 19.., 20.. or 21..: 13.. and 14.. too, the Shamsi years
	_shamsi = r"(19|20|21|13|14)"
	prefix, prefix2, prefix3, seq, month, suffix = (
		r"(?P<prefix1>.*?)", r"(?P<prefix2>\D)", r"(?P<prefix3>\D+?)", r"(?P<seq>\d*)", r"(?P<month>(0[1-9]|1[0-2]))", r"(?P<suffix>\D*?)"
	)
	year = rf"(?P<year>((?<=\D)|(?<=^))({_shamsi}\d{{2}}|(\d{{2}}(?=\D))))"
	year_end = rf"(?P<year_end>((?<=\D)|(?<=^))({_shamsi}\d{{2}}|(\d{{2}}(?=\D))))"
	_sequence_year_range_monthly_regex = rf"^{prefix}{year}{prefix2}{year_end}(?P<prefix3>\D){month}(?P<prefix4>\D+?){seq}{suffix}$"
	_sequence_year_range_regex = rf"^(?:{prefix}{year}{prefix2}{year_end}{prefix3})?{seq}{suffix}$"
	_sequence_monthly_regex = rf"^{prefix}{year}(?P<prefix2>\D*?){month}{prefix3}{seq}{suffix}$"
	_sequence_yearly_regex = rf"^{prefix}(?P<year>((?<=\D)|(?<=^))({_shamsi}?\d{{2}}))(?P<prefix2>\D+?){seq}{suffix}$"

	def _veron_shamsi(self):
		return self.company_id.country_id.code == "IR"

	def _veron_date(self):
		return fields.Date.to_date(self[self._sequence_date_field])

	def _get_sequence_date_range(self, reset):
		date = self._veron_date()
		if not self._veron_shamsi() or not date or reset not in ("year", "year_range", "month", "year_range_month"):
			return super()._get_sequence_date_range(reset)
		jy, jm, _jd = jalali.to_jalali(date)
		if reset in ("month", "year_range_month"):
			start = jalali.to_gregorian(jy, jm, 1)
			end = jalali.period_next(start, "month") - datetime.timedelta(days=1)
		else:
			start = jalali.to_gregorian(jy, 1, 1)
			end = jalali.to_gregorian(jy + 1, 1, 1) - datetime.timedelta(days=1)
		return start, end, jy, jy

	def _get_next_sequence_format(self):
		format_string, format_values = super()._get_next_sequence_format()
		date = self._veron_date()
		if self._veron_shamsi() and date and format_values.get("month"):
			format_values["month"] = jalali.to_jalali(date)[1]
		return format_string, format_values

	def _sequence_matches_date(self):
		self.ensure_one()
		date = self._veron_date()
		if not self._veron_shamsi() or not date or not self[self._sequence_field]:
			return super()._sequence_matches_date()
		format_values = self._get_sequence_format_param(self[self._sequence_field])[1]
		jy, jm, _jd = jalali.to_jalali(date)
		return (
			(not format_values["year"] or self._year_match(format_values["year"], jy))
			and (not format_values["year_end"] or self._year_match(format_values["year_end"], jy))
			and (not format_values["month"] or format_values["month"] == jm)
		)

	def _get_starting_sequence(self):
		sequence = super()._get_starting_sequence()
		date = self.date or self.invoice_date or fields.Date.context_today(self)
		if not self._veron_shamsi():
			return sequence
		# The year part Odoo put: «2026», or «25-26» for a fiscal year across two years
		parts = sequence.split("/")
		for i, part in enumerate(parts[:-1]):
			if part.isdigit() and len(part) == 4 or (len(part) == 5 and part[2] == "-"):
				parts[i] = str(jalali.to_jalali(date)[0])
				break
		return "/".join(parts)
