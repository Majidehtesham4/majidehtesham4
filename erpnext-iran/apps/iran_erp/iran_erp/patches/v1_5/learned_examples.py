"""Wordings learned before examples were reviewed («آموخته: …» chat commands) become proposed
examples: they are checked against the ERP and teach the assistant once approved."""

import frappe


def execute():
	from iran_erp.commands.learning import LEARNED_PREFIX, propose

	frappe.reload_doc("iran_erp", "doctype", "iran_intent_example")
	frappe.reload_doc("iran_erp", "doctype", "iran_ai_request")
	for command in frappe.get_all(
		"Iran Chat Command", filters={"learned": 1, "action": "Built-in Command"}, fields=["name", "intent", "phrases"]
	):
		if not command.name.startswith(LEARNED_PREFIX):
			continue
		for phrase in (command.phrases or "").splitlines():
			if phrase.strip():
				propose(command.intent, phrase.strip(), source="Earlier Learning")
		frappe.delete_doc("Iran Chat Command", command.name, ignore_permissions=True, force=True)
