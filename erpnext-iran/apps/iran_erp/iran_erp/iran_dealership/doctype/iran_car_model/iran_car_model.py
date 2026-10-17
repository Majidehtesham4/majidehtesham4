# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class IranCarModel(Document):
	def autoname(self):
		self.set_title()
		self.name = self.title

	def validate(self):
		self.set_title()

	def set_title(self):
		self.title = f"{(self.brand or '').strip()} {(self.model or '').strip()}".strip()
