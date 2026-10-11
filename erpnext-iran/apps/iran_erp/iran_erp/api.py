import frappe
from dateutil.relativedelta import relativedelta

from iran_erp.utils.jalali import format_jalali, jalali_year_bounds


@frappe.whitelist()
def get_jalali_date(date: str, fmt: str = "numeric") -> str:
	return format_jalali(date, fmt)


@frappe.whitelist()
def create_jalali_fiscal_year(jalali_year: int, company: str | None = None) -> str:
	"""Create a Fiscal Year from 1 Farvardin to the last day of Esfand of the given Jalali year."""
	frappe.has_permission("Fiscal Year", "create", throw=True)

	name = str(int(jalali_year))
	if frappe.db.exists("Fiscal Year", name):
		return name

	start, end = jalali_year_bounds(int(jalali_year))
	# ERPNext expects end = start + 1 Gregorian year - 1 day. Jalali years drift from that
	# by a day around leap years, so flag them as "short year" to skip that check.
	gregorian_length_matches = end == start + relativedelta(years=1) - relativedelta(days=1)
	fiscal_year = frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": name,
			"year_start_date": start,
			"year_end_date": end,
			"is_short_year": 0 if gregorian_length_matches else 1,
			"companies": [{"company": company}] if company else [],
		}
	)
	fiscal_year.insert()
	return fiscal_year.name
