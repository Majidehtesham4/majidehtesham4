import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	create_custom_fields(get_custom_fields(), update=True)
	setup_rial()


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
	return {doctype: iranian_ids for doctype in ("Customer", "Supplier", "Company")}


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
