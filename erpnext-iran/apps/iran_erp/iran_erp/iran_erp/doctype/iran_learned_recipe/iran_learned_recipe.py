# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class IranLearnedRecipe(Document):
	def on_update(self):
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()

	def on_trash(self):
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()
