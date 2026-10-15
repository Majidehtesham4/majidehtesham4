"""Jalali months in ERPNext's period reports.

Sales and Purchase Analytics, the "... Trends" reports, Stock Analytics and the financial statements
(Profit and Loss, Balance Sheet, Cash Flow) split time into Gregorian months: columns read
"Mar 2026" or "Mar (Amt)" and a month runs from the 21st to the 20th of the next. With Jalali dates
switched on (Iran ERP Settings) these functions are replaced so that months, quarters (seasons)
and half years follow the Jalali calendar and are labelled "مهر ۱۴۰۵". Weekly and yearly periods
are left as they are: fiscal years are already Jalali.

ERPNext offers no hook for this, so the functions are swapped on the first request (before_request
and before_job hooks); each one checks the setting on every call and falls back to the original.
"""

import datetime

import frappe
import jdatetime
from frappe.utils import add_days, getdate

from iran_erp.utils.jalali import MONTH_NAMES, to_persian_digits

STEPS = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6}
SEASONS = ("بهار", "تابستان", "پاییز", "زمستان")
_applied = False


def jalali_on() -> bool:
	value = frappe.db.get_single_value("Iran ERP Settings", "jalali_date_input")
	return value is None or bool(int(value))


def _jalali(date) -> jdatetime.date:
	return jdatetime.date.fromgregorian(date=getdate(date))


def _period_start(date, step: int) -> datetime.date:
	"""The first day of the Jalali month, season or half year that holds the date."""
	j = _jalali(date)
	month = (j.month - 1) // step * step + 1
	return jdatetime.date(j.year, month, 1).togregorian()


def _next_start(start, step: int) -> datetime.date:
	j = _jalali(start)
	month = (j.month - 1) // step * step + 1 + step
	year = j.year + (month - 1) // 12
	return jdatetime.date(year, (month - 1) % 12 + 1, 1).togregorian()


def jalali_ranges(from_date, to_date, step: int) -> list[tuple[datetime.date, datetime.date]]:
	"""(start, end) of each Jalali period between two dates; the first and last may be partial."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	ranges = []
	start = from_date
	while start <= to_date and len(ranges) < 120:
		end = min(add_days(_next_start(start, step), -1), to_date)
		ranges.append((start, end))
		start = add_days(end, 1)
	return ranges


def period_label(date, step: int) -> str:
	""" "مهر ۱۴۰۵", "پاییز ۱۴۰۵" or "نیمه دوم ۱۴۰۵" for the period that holds the date."""
	j = _jalali(date)
	if step == 12:
		return to_persian_digits(j.year)
	if step == 3:
		name = SEASONS[(j.month - 1) // 3]
	elif step == 6:
		name = "نیمه اول" if j.month <= 6 else "نیمه دوم"
	else:
		name = MONTH_NAMES[j.month - 1]
	return f"{name} {to_persian_digits(j.year)}"


def range_label(from_date, to_date) -> str:
	start, end = _jalali(from_date), _jalali(to_date)
	if (start.year, start.month) == (end.year, end.month):
		return f"{MONTH_NAMES[start.month - 1]} {to_persian_digits(start.year)}"
	if start.year == end.year:
		return (
			f"{MONTH_NAMES[start.month - 1]} تا {MONTH_NAMES[end.month - 1]} {to_persian_digits(start.year)}"
		)
	return (
		f"{MONTH_NAMES[start.month - 1]} {to_persian_digits(start.year)} تا "
		f"{MONTH_NAMES[end.month - 1]} {to_persian_digits(end.year)}"
	)


# ---- Sales and Purchase Analytics


def _analytics(original_ranges, original_period):
	def get_period_date_ranges(self):
		step = STEPS.get(self.filters.range)
		if not step or not jalali_on():
			return original_ranges(self)
		from_date = _period_start(self.filters.from_date, step)
		self.periodic_daterange = [
			end for _start, end in jalali_ranges(from_date, self.filters.to_date, step)
		]

	def get_period(self, posting_date):
		step = STEPS.get(self.filters.range)
		if not step or not jalali_on():
			return original_period(self, posting_date)
		return period_label(posting_date, step)

	return get_period_date_ranges, get_period


# ---- "... Trends" reports


def _trends(original_ranges, original_columns):
	def get_period_date_ranges(period, fiscal_year=None, year_start_date=None):
		step = STEPS.get(period)
		if not step or not jalali_on():
			return original_ranges(period, fiscal_year, year_start_date)
		if year_start_date:
			year_end_date = add_days(_next_start(_period_start(year_start_date, 12), 12), -1)
		else:
			year_start_date, year_end_date = frappe.get_cached_value(
				"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"]
			)
		return [list(r) for r in jalali_ranges(year_start_date, year_end_date, step)]

	def get_period_wise_columns(bet_dates, period, pwc):
		if not STEPS.get(period) or not jalali_on():
			return original_columns(bet_dates, period, pwc)
		from frappe import _

		label = range_label(bet_dates[0], bet_dates[1])
		pwc += [
			f"{label} ({_('Qty')}):Float:120",
			f"{label} ({_('Amt')}):Currency/currency:120",
		]

	return get_period_date_ranges, get_period_wise_columns


# ---- Stock Analytics, Job Card Summary, Work Order Summary


def _stock(original_ranges, original_period):
	def get_period_date_ranges(filters):
		step = STEPS.get(filters.range)
		if not step or not jalali_on():
			return original_ranges(filters)
		from_date = _period_start(filters.from_date, step)
		return [list(r) for r in jalali_ranges(from_date, filters.to_date, step)]

	def get_period(posting_date, filters):
		step = STEPS.get(filters.range)
		if not step or not jalali_on():
			return original_period(posting_date, filters)
		return period_label(posting_date, step)

	return get_period_date_ranges, get_period


# ---- Profit and Loss, Balance Sheet, Cash Flow


def _financial(original_period_list, original_label):
	def get_period_list(
		from_fiscal_year,
		to_fiscal_year,
		period_start_date,
		period_end_date,
		filter_based_on,
		periodicity,
		accumulated_values=False,
		company=None,
		reset_period_on_fy_change=True,
		ignore_fiscal_year=False,
	):
		periods = original_period_list(
			from_fiscal_year,
			to_fiscal_year,
			period_start_date,
			period_end_date,
			filter_based_on,
			periodicity,
			accumulated_values,
			company,
			reset_period_on_fy_change,
			ignore_fiscal_year,
		)
		step = STEPS.get(periodicity)
		if not step or not periods or not jalali_on():
			return periods
		from erpnext.accounts.utils import get_fiscal_year

		year_start_date, year_end_date = periods[0].year_start_date, periods[0].year_end_date
		result = []
		for start, end in jalali_ranges(year_start_date, year_end_date, step):
			period = frappe._dict(from_date=start, to_date=end)
			if not ignore_fiscal_year:
				period.to_date_fiscal_year = get_fiscal_year(end, company=company)[0]
				period.from_date_fiscal_year_start_date = get_fiscal_year(start, company=company)[1]
			result.append(period)
		for period in result:
			j = _jalali(period.to_date)
			if accumulated_values:
				first = (
					period.from_date_fiscal_year_start_date
					if reset_period_on_fy_change and not ignore_fiscal_year
					else result[0].from_date
				)
				label = range_label(first, period.to_date)
			elif step == 1:
				label = range_label(period.to_date, period.to_date)
			else:
				label = period_label(period.to_date, step)
			period.update(
				{
					"key": f"j{j.year}_{j.month:02d}",
					"label": label,
					"year_start_date": year_start_date,
					"year_end_date": year_end_date,
				}
			)
		return result

	def get_label(periodicity, from_date, to_date):
		if periodicity != "Yearly" or not jalali_on():
			return original_label(periodicity, from_date, to_date)
		start, end = _jalali(from_date).year, _jalali(to_date).year
		return to_persian_digits(start if start == end else f"{start}-{end}")

	return get_period_list, get_label


# ---- Dashboard charts and everything else that buckets dates with frappe.utils.dateutils

GRAINS = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}
DATEUTILS = ("get_period", "get_period_beginning", "get_period_ending", "get_dates_from_timegrain")


def _dateutils(originals):
	"""Monthly, quarterly and yearly buckets follow the Jalali calendar: «مهر ۱۴۰۵» instead of «Oct 2026»."""

	def get_period_ending(date, timegrain):
		step = GRAINS.get(timegrain)
		if not step or not jalali_on():
			return originals["get_period_ending"](date, timegrain)
		return add_days(_next_start(getdate(date), step), -1)

	def get_period_beginning(date, timegrain, as_str=True):
		step = GRAINS.get(timegrain)
		if not step or not jalali_on():
			return originals["get_period_beginning"](date, timegrain, as_str)
		return _period_start(getdate(date), step)

	def get_period(date, interval="Monthly"):
		step = GRAINS.get(interval)
		if not step or not jalali_on():
			return originals["get_period"](date, interval)
		return period_label(date, step)

	def get_dates_from_timegrain(from_date, to_date, timegrain="Daily"):
		step = GRAINS.get(timegrain)
		if not step or not jalali_on():
			return originals["get_dates_from_timegrain"](from_date, to_date, timegrain)
		dates = [get_period_ending(from_date, timegrain)]
		while getdate(dates[-1]) < getdate(to_date) and len(dates) < 240:
			dates.append(get_period_ending(add_days(dates[-1], 1), timegrain))
		return dates

	return {
		"get_period": get_period,
		"get_period_beginning": get_period_beginning,
		"get_period_ending": get_period_ending,
		"get_dates_from_timegrain": get_dates_from_timegrain,
	}


def _patch_dateutils():
	import sys

	from frappe.utils import dateutils

	originals = {name: getattr(dateutils, name) for name in DATEUTILS}
	patched = _dateutils(originals)
	for name, function in patched.items():
		setattr(dateutils, name, function)
	# Modules that imported the functions by name before this ran keep their own references
	for module_name, module in list(sys.modules.items()):
		if not module or not module_name.startswith(("frappe", "erpnext")):
			continue
		for name in DATEUTILS:
			if getattr(module, name, None) is originals[name]:
				setattr(module, name, patched[name])


def apply():
	"""Swap in the Jalali versions once per process."""
	global _applied
	if _applied:
		return
	_applied = True
	try:
		from erpnext.accounts.report import financial_statements
		from erpnext.controllers import trends
		from erpnext.selling.report.sales_analytics.sales_analytics import Analytics
		from erpnext.stock.report.stock_analytics import stock_analytics
	except ImportError:
		return

	Analytics.get_period_date_ranges, Analytics.get_period = _analytics(
		Analytics.get_period_date_ranges, Analytics.get_period
	)
	trends.get_period_date_ranges, trends.get_period_wise_columns = _trends(
		trends.get_period_date_ranges, trends.get_period_wise_columns
	)
	stock_analytics.get_period_date_ranges, stock_analytics.get_period = _stock(
		stock_analytics.get_period_date_ranges, stock_analytics.get_period
	)
	financial_statements.get_period_list, financial_statements.get_label = _financial(
		financial_statements.get_period_list, financial_statements.get_label
	)
	_patch_dateutils()
