"""The customer's booking page (/my/bookings/.../schedule) in Shamsi: OCA's resource_booking draws a
Gregorian month in Python; for a Persian visitor the month is a Shamsi one, its URL holds the Shamsi
year and month (/schedule/1405/8), and the days and dates are Shamsi."""

import calendar
import datetime

from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.addons.veron_core.models import jalali


# The weekdays by Odoo's numbers (1 = Monday), written out: Odoo's Persian has «1‌شنبه»
WEEKDAYS = {"1": "دوشنبه", "2": "سه‌شنبه", "3": "چهارشنبه", "4": "پنجشنبه", "5": "جمعه", "6": "شنبه", "7": "یکشنبه"}


class ShamsiMonth:
	"""The Shamsi month of a booking page: what the page's template asks of Python's calendar"""

	def __init__(self, first_weekday, first, length):
		self._calendar = calendar.Calendar(first_weekday)
		self.first = first
		self.last = first + datetime.timedelta(days=length - 1)
		self.days = {first + datetime.timedelta(days=i) for i in range(length)}

	def iterweekdays(self):
		return self._calendar.iterweekdays()

	def monthdatescalendar(self, *_args):
		"""The weeks of the month, whole: from the week start before its 1st to the week end after its last day"""
		start = self.first - datetime.timedelta(days=(self.first.weekday() - self._calendar.firstweekday) % 7)
		weeks = []
		while start <= self.last:
			weeks.append([start + datetime.timedelta(days=i) for i in range(7)])
			start += datetime.timedelta(days=7)
		return weeks


class ResourceBooking(models.Model):
	_inherit = "resource.booking"

	def _get_calendar_context(self, year=None, month=None, now=None):
		if not (self.env.lang or "").startswith("fa"):
			values = super()._get_calendar_context(year, month, now)
			start = values["start"]
			date_format = values["res_lang"].date_format
			values.update({
				"month_days": {d for week in values["calendar"].monthdatescalendar(start.year, start.month) for d in week if d.month == start.month},
				"month_title": start.strftime("%B %Y"),
				"next_month": start + relativedelta(months=1),
				"previous_month": start - relativedelta(months=1),
				"day_label": lambda day: day.day,
				"format_day": lambda moment: moment.strftime(date_format),
			})
			return values
		now = fields.Datetime.context_timestamp(self, now or fields.Datetime.now())
		if year and year > 1700:
			# A Gregorian month, from an old link: its Shamsi month
			year, month = jalali.to_jalali(datetime.date(year, month or 1, 1))[:2]
		elif not year:
			year, month = jalali.to_jalali(now.date())[:2]
		month = month or 1
		first = jalali.to_gregorian(year, month, 1)
		length = jalali.month_length(year, month)
		start = now.replace(year=first.year, month=first.month, day=first.day, hour=0, minute=0, second=0, microsecond=0)
		lang = self.env["res.lang"]._lang_get(self.env.lang or self.env.user.lang)
		booking_duration = datetime.timedelta(hours=self.duration)
		slots = self._get_available_slots(start, start + datetime.timedelta(days=length) + booking_duration)
		month_calendar = ShamsiMonth(int(lang.week_start) - 1, first, length)
		after = (year + month // 12, month % 12 + 1)
		before = (year - (month == 1), 12 if month == 1 else month - 1)
		return {
			"booking": self,
			"calendar": month_calendar,
			"now": now,
			"res_lang": lang,
			"slots": slots,
			"start": start,
			"weekday_names": WEEKDAYS,
			"month_days": month_calendar.days,
			"month_title": f"{jalali.MONTHS[month - 1]} {year}",
			"next_month": _Month(*after),
			"previous_month": _Month(*before),
			"day_label": lambda day: jalali.to_jalali(day)[2],
			"format_day": lambda moment: "%04d/%02d/%02d" % jalali.to_jalali(moment),
		}


class _Month:
	"""A Shamsi year and month, for the template's links"""

	def __init__(self, year, month):
		self.year = year
		self.month = month
