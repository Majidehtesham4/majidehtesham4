"""A fresh site made ready in one command, without the setup wizard in the browser:

	bench --site frontend execute iran_erp.fresh_start.run

On a new, empty site this does what the setup wizard does, with the Iranian choices (Persian,
Iran, Asia/Tehran, rial, the Iranian chart of accounts, this Jalali year as the fiscal year). The
first login then opens Easy Setup, which asks about the business and arranges the system for it.

The business's name comes from the IRAN_COMPANY environment variable (the scripts in deploy/ set
it), so that a Persian name needs no quoting on the command line; IRAN_DEMO=1 also loads the car
dealership's sample data.
"""

import os

import frappe
import jdatetime
from frappe.utils import cint, getdate, nowdate

from iran_erp.accounts.chart import CHART_NAME
from iran_erp.utils.jalali import jalali_year_bounds


def run(company: str | None = None, abbr: str | None = None, demo: bool | None = None) -> str:
	frappe.only_for("System Manager")
	company = (company or os.environ.get("IRAN_COMPANY") or "شرکت من").strip()
	abbr = (abbr or os.environ.get("IRAN_ABBR") or "CO").strip().upper()[:5]
	demo = cint(os.environ.get("IRAN_DEMO")) if demo is None else cint(demo)
	if not frappe.is_setup_complete():
		_setup(company, abbr)
	company = frappe.defaults.get_global_default("company") or company
	if demo:
		from iran_erp.iran_dealership.demo import _records, create_dealership_demo

		if not _records():
			create_dealership_demo(company)
	frappe.db.commit()
	return f"Ready: {company}"


def _setup(company: str, abbr: str):
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	jalali_year = jdatetime.date.fromgregorian(date=getdate(nowdate())).year
	start, end = jalali_year_bounds(jalali_year)
	result = setup_complete(
		{
			"language": "فارسی",
			"lang": "فارسی",
			"country": "Iran",
			"timezone": "Asia/Tehran",
			"currency": "IRR",
			"company_name": company,
			"company_abbr": abbr,
			"chart_of_accounts": CHART_NAME,
			"fy_start_date": str(start),
			"fy_end_date": str(end),
			"enable_telemetry": 0,
		}
	)
	if (result or {}).get("status") != "ok":
		frappe.throw(f"Setup did not finish: {result}")
	frappe.db.set_single_value("System Settings", {"language": "fa", "time_zone": "Asia/Tehran"})
	frappe.db.set_value("User", "Administrator", "language", "fa")
	frappe.db.set_single_value("Iran ERP Settings", "trade_name", company)

	from iran_erp.install import jalali_fiscal_year_names

	# The fiscal year ERPNext made (1 Farvardin to the end of Esfand) takes its Jalali name
	jalali_fiscal_year_names()
	frappe.db.commit()
	frappe.clear_cache()
