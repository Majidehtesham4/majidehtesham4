import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from iran_erp.accounts.chart import install_chart_template


def after_install():
	create_custom_fields(get_custom_fields(), update=True)
	setup_rial()
	install_chart_template()
	from iran_erp.desktop import use_icon_grid

	# The home page is a grid of the business's icons, not the «Apps» page of two app folders
	use_icon_grid()
	no_update_notices()
	from iran_erp.owner import record_code_version

	record_code_version()


def no_update_notices():
	"""Customers are not told about new versions of the software underneath, nor shown its change
	log: updates are made centrally, for every business at once (deploy/update.ps1)."""
	frappe.db.set_single_value(
		"System Settings",
		{"disable_system_update_notification": 1, "disable_change_log_notification": 1},
	)


def get_custom_fields():
	iranian_ids = [
		{
			"fieldname": "iran_national_id",
			"label": "National ID / کد ملی یا شناسه ملی",
			"fieldtype": "Data",
			"insert_after": "tax_id",
			"description": "10 digits for individuals, 11 digits for legal entities",
		},
		{
			"fieldname": "iran_economic_code",
			"label": "Economic Code / کد اقتصادی",
			"fieldtype": "Data",
			"insert_after": "iran_national_id",
		},
	]
	fields = {doctype: list(iranian_ids) for doctype in ("Customer", "Supplier", "Company")}
	# Electronic invoices for the tax organization (سامانه مؤدیان)
	fields["Item"] = [
		{
			"fieldname": "iran_sstid",
			"label": "Product/Service ID (Moadian)",
			"fieldtype": "Data",
			"length": 13,
			"insert_after": "item_group",
			"description": "13-digit product or service ID from the tax organization's catalogue",
		}
	]
	fields["UOM"] = [
		{
			"fieldname": "iran_moadian_unit_code",
			"label": "Moadian Unit Code",
			"fieldtype": "Data",
			"insert_after": "uom_name",
			"description": "Unit of measure code in the tax organization's list",
		}
	]
	fields["Sales Invoice"] = [
		{
			"fieldname": "iran_tax_id",
			"label": "Tax Number (Moadian)",
			"fieldtype": "Data",
			"insert_after": "due_date",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "iran_moadian_serial",
			"label": "Moadian Serial",
			"fieldtype": "Int",
			"insert_after": "iran_tax_id",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
			"hidden": 1,
		},
	]
	return fields


def refresh_module_map():
	"""Read the apps' modules afresh before the DocTypes are synced.

	A migrate takes its list of modules from the cache as it was when the command started. An
	update that adds a module (Iran Dealership) was then synced without that module's DocTypes,
	and everything that needed them failed («No module named frappe.core.doctype.iran_car_model»).
	"""
	frappe.cache.delete_value(["app_modules", "module_app"])
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map()


def setup_rial():
	"""The rial has no subunit in practice, so show and round IRR amounts without decimals.

	Amounts are written as Iranian accounting writes them: the number, then the word «ریال»
	(«۳۵٬۰۰۰ ریال»), rather than the ligature sign «﷼» before the number.
	"""
	if frappe.db.exists("Currency", "IRR"):
		frappe.db.set_value(
			"Currency",
			"IRR",
			{
				"symbol": "ریال",
				"symbol_on_right": 1,
				"number_format": "#,###",
				"fraction": "",
				"fraction_units": 0,
				"smallest_currency_fraction_value": 1,
			},
		)
		# Without this the system-wide number format (with two decimals) is used for every currency.
		# The desk reads it from the defaults that saving System Settings would normally write.
		frappe.db.set_single_value("System Settings", "use_number_format_from_currency", 1)
		frappe.db.set_default("use_number_format_from_currency", 1)


def clear_translation_cache():
	"""New or changed Persian translations only show once the cached dictionaries are rebuilt."""
	from frappe.translate import clear_cache

	clear_cache()


# Master records ERPNext creates under English names: show them translated wherever they appear
TRANSLATED_DOCTYPES = (
	"Territory",
	"Customer Group",
	"Supplier Group",
	"Item Group",
	"UOM",
	"Mode of Payment",
	"Price List",
	"Warehouse Type",
	"Sales Stage",
	"Lead Source",
	"Opportunity Type",
	"Opportunity Lost Reason",
	"Market Segment",
	"Industry Type",
	"Designation",
	"Activity Type",
	"Project Type",
	"Stock Entry Type",
	"Salutation",
	"Gender",
	"Print Heading",
	"Print Format",
	"Account Category",
	"Financial Report Template",
	"Warehouse",
	"Department",
	"Cost Center",
	"UOM Category",
)


def mark_translated_doctypes():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype in TRANSLATED_DOCTYPES:
		if not frappe.db.exists("DocType", doctype) or frappe.get_meta(doctype).translated_doctype:
			continue
		make_property_setter(
			doctype,
			None,
			"translated_doctype",
			1,
			"Check",
			for_doctype=True,
			validate_fields_for_doctype=False,
		)


BRAND = "ERP-VERON"
BRAND_LOGO = "/assets/iran_erp/images/erp-veron-logo.svg"
BRAND_WEBSITE = "https://erpveron.com"
# Values that are still the stock ones and can be replaced; anything else was set by the user
STOCK_NAMES = {None, "", "ERPNext", "Frappe", "Frappe Framework"}


def apply_branding():
	"""Show the product as ERP-VERON: name in titles and the login page, logo and favicon."""
	if frappe.db.get_single_value("System Settings", "app_name") in STOCK_NAMES:
		frappe.db.set_single_value("System Settings", "app_name", BRAND)
	website = frappe.get_single("Website Settings")
	changes = {}
	if website.app_name in STOCK_NAMES:
		changes["app_name"] = BRAND
	for field in ("app_logo", "favicon", "splash_image"):
		if not website.get(field):
			changes[field] = BRAND_LOGO
	if not website.footer_powered:
		changes["footer_powered"] = BRAND
	if changes:
		# Saving Website Settings clears the whole cache; setting the values does not
		for field, value in changes.items():
			frappe.db.set_single_value("Website Settings", field, value)
	if not frappe.db.get_single_value("Navbar Settings", "app_logo"):
		frappe.db.set_single_value("Navbar Settings", "app_logo", BRAND_LOGO)
	# The Help menu's link to the framework makers' support site leads to the product's website
	for item in frappe.get_all(
		"Navbar Item",
		filters={"parent": "Navbar Settings", "route": ["like", "%frappe.io%"]},
		pluck="name",
	):
		frappe.db.set_value("Navbar Item", item, {"item_label": "ERP-VERON Website", "route": BRAND_WEBSITE})


# ERPNext's «Review» report (Quality) reads Quality Action.document_type, a column the doctype no
# longer has, and fails with a database error. It now links the review in its own field.
REVIEW_REPORT_QUERY = """SELECT
  `tabQuality Action`.name as "Quality Action:Link/Quality Action:200",
  `tabQuality Action`.corrective_preventive as "Action:Data:150",
  `tabQuality Action`.review as "Quality Review:Link/Quality Review:200",
  `tabQuality Action`.date as "Date:Date:120",
  `tabQuality Action`.status as "Status:Data:120"
FROM
  `tabQuality Action`
WHERE
  ifnull(`tabQuality Action`.review, '') != ''"""


def fix_upstream_reports():
	if not frappe.db.exists("Report", "Review"):
		return
	query = frappe.db.get_value("Report", "Review", "query") or ""
	if "document_type" in query and frappe.db.has_column("Quality Action", "review"):
		frappe.db.set_value("Report", "Review", "query", REVIEW_REPORT_QUERY, update_modified=False)


def jalali_fiscal_year_names():
	"""A fiscal year that runs exactly from 1 Farvardin to the end of Esfand but has a Gregorian
	name («2026-2027», made by ERPNext's setup) is renamed to its Jalali year («1405»)."""
	import re

	import jdatetime

	from iran_erp.utils.jalali import jalali_year_bounds

	for year in frappe.get_all("Fiscal Year", fields=["name", "year_start_date", "year_end_date"]):
		if not re.fullmatch(r"\d{4}(-\d{4})?", year.name) or 1300 < int(year.name[:4]) < 1500:
			continue
		jalali_year = jdatetime.date.fromgregorian(date=year.year_start_date).year
		start, end = jalali_year_bounds(jalali_year)
		new_name = str(jalali_year)
		if (start, end) != (year.year_start_date, year.year_end_date) or frappe.db.exists(
			"Fiscal Year", new_name
		):
			continue
		frappe.rename_doc("Fiscal Year", year.name, new_name, force=True, show_alert=False)
		frappe.db.set_value("Fiscal Year", new_name, "year", new_name, update_modified=False)


# Records ERPNext makes for every company under English names with the company's abbreviation
# («Stores - ST», «Accounts - ST», «Main - ST»). Their names differ per company, so their Persian
# names are added as translations for each company on migrate.
COMPANY_RECORDS = {
	"Warehouse": {
		"All Warehouses": "همه‌ی انبارها",
		"Stores": "انبار اصلی",
		"Finished Goods": "انبار کالای ساخته‌شده",
		"Work In Progress": "انبار کالای در جریان ساخت",
		"Goods In Transit": "کالای در راه",
	},
	"Department": {
		"All Departments": "همه‌ی بخش‌ها",
		"Accounts": "حسابداری",
		"Marketing": "بازاریابی",
		"Sales": "فروش",
		"Purchase": "خرید",
		"Operations": "عملیات",
		"Production": "تولید",
		"Dispatch": "ارسال",
		"Customer Service": "خدمات مشتریان",
		"Human Resources": "منابع انسانی",
		"Management": "مدیریت",
		"Quality Management": "مدیریت کیفیت",
		"Research & Development": "تحقیق و توسعه",
		"Legal": "حقوقی",
	},
	"Cost Center": {"Main": "اصلی"},
}


def translate_company_records():
	for abbr in frappe.get_all("Company", pluck="abbr"):
		for doctype, names in COMPANY_RECORDS.items():
			for english, persian in names.items():
				source = f"{english} - {abbr}"
				if not frappe.db.exists(doctype, source):
					continue
				if frappe.db.exists("Translation", {"language": "fa", "source_text": source}):
					continue
				frappe.get_doc(
					{
						"doctype": "Translation",
						"language": "fa",
						"source_text": source,
						"translated_text": f"{persian} - {abbr}",
					}
				).insert(ignore_permissions=True)


def on_company_update(doc, method=None):
	"""A new company's warehouses, departments and cost center get their Persian names too."""
	translate_company_records()
