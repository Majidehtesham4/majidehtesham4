"""A fresh site made ready in one command, without the setup wizard in the browser:

	bench --site frontend execute iran_erp.fresh_start.run

On a new, empty site this does what the setup wizard does, with the Iranian choices (Persian,
Iran, Asia/Tehran, rial, the Iranian chart of accounts, this Jalali year as the fiscal year), and
then loads the car dealership's sample data. Run on a site already set up, it only loads the
sample data that is missing.
"""

import frappe
import jdatetime
from frappe.utils import getdate, nowdate

from iran_erp.accounts.chart import CHART_NAME
from iran_erp.utils.jalali import jalali_year_bounds


def run(
	company: str = "نمایشگاه خودرو ورون",
	abbr: str = "VRN",
	general_demo: bool = False,
) -> str:
	frappe.only_for("System Manager")
	if not frappe.is_setup_complete():
		_setup(company, abbr)
	company = frappe.defaults.get_global_default("company") or company

	from iran_erp.iran_dealership.demo import _records, create_dealership_demo

	if general_demo:
		from iran_erp.demo import create_demo_data

		create_demo_data(company)
	if not _records():
		create_dealership_demo(company)
	frappe.db.commit()
	return f"Ready: {company}. Log in as Administrator; the showroom website is at /cars."


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
