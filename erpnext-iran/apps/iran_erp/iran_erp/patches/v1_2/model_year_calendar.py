"""Imported car models are marked as imported, and the model year of their cars, written in Jalali
before, becomes Gregorian (1396 → 2017)."""

import frappe

from iran_erp.iran_dealership.seed import IMPORTED_BRANDS


def execute():
	if not frappe.db.table_exists("Iran Car Model"):
		return
	frappe.db.set_value("Iran Car Model", {"brand": ("in", IMPORTED_BRANDS)}, "made_in", "Imported Car")
	frappe.db.set_value("Iran Car Model", {"made_in": ("!=", "Imported Car")}, "made_in", "Made in Iran")
	made_in = dict(frappe.get_all("Iran Car Model", fields=["name", "made_in"], as_list=True))
	for car in frappe.get_all("Iran Vehicle", fields=["name", "car_model", "year"]):
		values = {"made_in": made_in.get(car.car_model) or "Made in Iran"}
		year = (car.year or "").strip()
		if values["made_in"] == "Imported Car" and year.isdigit() and int(year) < 1500:
			values["year"] = str(int(year) + 621)
		frappe.db.set_value("Iran Vehicle", car.name, values, update_modified=False)
