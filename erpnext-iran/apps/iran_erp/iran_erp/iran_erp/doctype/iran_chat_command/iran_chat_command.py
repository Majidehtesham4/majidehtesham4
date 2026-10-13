# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class IranChatCommand(Document):
	def validate(self):
		if self.filters:
			try:
				json.loads(self.filters)
			except ValueError:
				frappe.throw(_("Filters must be valid JSON"))
		if self.action == "Built-in Command":
			from iran_erp.commands.engine import INTENT_BY_NAME

			if self.intent not in INTENT_BY_NAME:
				frappe.throw(_("Choose one of the built-in commands"))

	def on_update(self):
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()

	def on_trash(self):
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()


@frappe.whitelist()
def builtin_commands() -> list[dict]:
	from iran_erp.commands.engine import describe

	return [{"value": row["name"], "label": row["title"]} for row in describe()]
