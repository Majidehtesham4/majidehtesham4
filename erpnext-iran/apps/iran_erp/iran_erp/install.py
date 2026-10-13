import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from iran_erp.accounts.chart import install_chart_template


def after_install():
	create_custom_fields(get_custom_fields(), update=True)
	setup_rial()
	install_chart_template()


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


def setup_rial():
	"""The rial has no subunit in practice, so show and round IRR amounts without decimals."""
	if frappe.db.exists("Currency", "IRR"):
		frappe.db.set_value(
			"Currency",
			"IRR",
			{
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
