# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class IranShowroomSettings(Document):
	def validate(self):
		months = month_options(self.months_options)
		if not months:
			frappe.throw(_("Write the instalment months offered, for example 6,10,12"))
		self.months_options = ",".join(str(m) for m in months)


def month_options(text) -> list[int]:
	"""«6، 10, 12» → [6, 10, 12]: Persian or Latin digits, separated by commas."""
	text = (text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹،", "0123456789,"))
	return sorted({cint(part) for part in text.split(",") if 0 < cint(part) <= 120})
