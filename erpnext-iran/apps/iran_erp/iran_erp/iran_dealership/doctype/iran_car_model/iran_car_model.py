# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# The technical specifications shown with every car of a model: field, label, unit
SPECS = (
	("engine", "Engine", ""),
	("engine_volume", "Engine Volume", "cc"),
	("cylinders", "Cylinders", ""),
	("power_hp", "Power", "hp"),
	("torque_nm", "Torque", "Nm"),
	("transmission", "Gearbox", ""),
	("gears", "Gears", ""),
	("fuel_type", "Fuel", ""),
	("fuel_consumption", "Fuel Consumption", "L/100 km"),
	("fuel_tank", "Fuel Tank", "litres"),
	("drive", "Drive", ""),
	("seats", "Seats", ""),
	("top_speed", "Top Speed", "km/h"),
	("acceleration", "0 to 100 km/h", "seconds"),
	("airbags", "Airbags", ""),
	("length_mm", "Length", "millimetres"),
	("trunk_volume", "Trunk", "litres"),
)


class IranCarModel(Document):
	def autoname(self):
		self.set_title()
		self.name = self.title

	def validate(self):
		self.set_title()

	def set_title(self):
		self.title = f"{(self.brand or '').strip()} {(self.model or '').strip()}".strip()


def spec_rows(model: str | None) -> list[dict]:
	"""The model's specifications that are filled in, as label and value in the user's language:
	[{"label": "حجم موتور", "value": "۱۵۸۷ سی‌سی"}, ...]"""
	from iran_erp.utils.jalali import to_persian_digits

	if not model or not frappe.db.exists("Iran Car Model", model):
		return []
	doc = frappe.get_cached_doc("Iran Car Model", model)
	rows = []
	for field, label, unit in SPECS:
		value = doc.get(field)
		if value in (None, "", 0, 0.0):
			continue
		if isinstance(value, float):
			value = f"{flt(value, 1):g}"
		text = _(str(value)) if isinstance(value, str) else str(value)
		if unit:
			text = f"{text} {_(unit)}"
		# An engine code («TU3», «EF7») keeps its Latin digits
		rows.append({"label": _(label), "value": text if field == "engine" else to_persian_digits(text)})
	return rows


def spec_features(model: str | None) -> list[str]:
	"""The model's other features, one per line in «Other Features»."""
	if not model or not frappe.db.exists("Iran Car Model", model):
		return []
	note = frappe.get_cached_doc("Iran Car Model", model).spec_note or ""
	return [line.strip() for line in note.splitlines() if line.strip()]


@frappe.whitelist()
def get_specs(model: str) -> dict:
	frappe.has_permission("Iran Car Model", "read", throw=True)
	return {"rows": spec_rows(model), "features": spec_features(model)}
