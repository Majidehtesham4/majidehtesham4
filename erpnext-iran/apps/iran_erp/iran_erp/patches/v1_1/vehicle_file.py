"""Cars registered with the first version of the dealership pack, in the car file of this one:
the model and colour as list entries, the lot status, the investor of an investor's car, the
entry date, and their costs as services."""

import frappe

from iran_erp.iran_dealership.seed import seed

STATUS = {"Available": "Ready for Sale"}


def execute():
	if not frappe.db.table_exists("Iran Vehicle"):
		return
	seed()
	# Cars are coded CAR-00001 now; the series of the first version was kept as an override
	frappe.db.delete("Property Setter", {"doc_type": "Iran Vehicle", "field_name": "naming_series"})
	frappe.clear_cache(doctype="Iran Vehicle")
	has_model = frappe.db.has_column("Iran Vehicle", "model")
	fields = [
		"name",
		"car_model",
		"color",
		"status",
		"ownership",
		"investment_contract",
		"investor",
		"entry_date",
		"purchase_date",
		"creation",
	]
	if has_model:
		fields.append("model")
	for car in frappe.get_all("Iran Vehicle", fields=fields):
		values = {}
		if not car.car_model and car.get("model"):
			title = f"سایر {car.model}"
			if not frappe.db.exists("Iran Car Model", title):
				frappe.get_doc({"doctype": "Iran Car Model", "brand": "سایر", "model": car.model}).insert(
					ignore_permissions=True
				)
			values["car_model"] = title
		if car.color and not frappe.db.exists("Iran Car Color", car.color):
			frappe.get_doc({"doctype": "Iran Car Color", "color_name": car.color}).insert(
				ignore_permissions=True
			)
		if car.status in STATUS:
			values["status"] = STATUS[car.status]
		if car.ownership == "Investor" and car.investment_contract and not car.investor:
			values["investor"] = frappe.db.get_value(
				"Iran Investment Contract", car.investment_contract, "investor"
			)
		if not car.entry_date:
			values["entry_date"] = car.purchase_date or car.creation.date()
		if values:
			frappe.db.set_value("Iran Vehicle", car.name, values, update_modified=False)
	other = "سایر هزینه‌ها"
	frappe.db.sql(
		"""update `tabIran Vehicle Cost` set service = %s, category = 'Other', status = 'Done'
		where ifnull(service, '') = ''""",
		other,
	)
