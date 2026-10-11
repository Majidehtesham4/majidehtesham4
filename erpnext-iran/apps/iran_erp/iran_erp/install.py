from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	create_custom_fields(get_custom_fields(), update=True)


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
