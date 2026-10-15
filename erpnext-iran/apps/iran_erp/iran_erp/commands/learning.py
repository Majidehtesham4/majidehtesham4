"""Learn new ways of asking for a command, so the next time the same request needs no AI model.

Sentences are learned when
- the AI model handled a request and created one kind of document that a command also creates
  (for example a draft Payment Entry of type Receive is the receive_payment command), or
- the user picked a command from the "which one did you mean?" list.

They are kept in Iran Chat Command, one "learned" record per command, where an administrator can
review, edit or delete them. Names of customers, suppliers and items are taken out first, so the
sentence teaches the wording, not the particular names.
"""

import frappe

from iran_erp.commands.text import find_numbers, tokens, yes_no

LEARNED_PREFIX = "آموخته: "
MAX_PHRASES = 300
MIN_WORDS = 3
# Already understood this well: nothing to learn
KNOWN_SCORE = 0.8
# How far back a short follow-up ("بله", "علی") looks for the request it answered
LOOK_BACK = 3


def _intent_for(doctype: str, name: str) -> str | None:
	simple = {
		"Sales Invoice": "create_sales_invoice",
		"Purchase Invoice": "create_purchase_invoice",
		"Quotation": "create_quotation",
		"Sales Order": "create_sales_order",
		"Purchase Order": "create_purchase_order",
		"Customer": "create_customer",
		"Supplier": "create_supplier",
		"Item": "create_item",
		"Lead": "create_lead",
		"Material Request": "create_material_request",
		"Work Order": "create_work_order",
		"ToDo": "create_todo",
	}
	if doctype in simple:
		return simple[doctype]
	if not frappe.db.exists(doctype, name):
		return None
	if doctype == "Payment Entry":
		kind = frappe.db.get_value(doctype, name, "payment_type")
		return {"Receive": "receive_payment", "Pay": "make_payment"}.get(kind)
	if doctype == "Iran Cheque":
		kind = frappe.db.get_value(doctype, name, "cheque_type")
		return {"Received": "register_received_cheque", "Issued": "register_issued_cheque"}.get(kind)
	if doctype == "Stock Entry":
		purpose, remarks = frappe.db.get_value(doctype, name, ["purpose", "remarks"])
		# Opening stock of items the AI model has just defined
		if remarks and "AI assistant" in remarks:
			return "create_item"
		return {
			"Material Receipt": "stock_receipt",
			"Material Issue": "stock_issue",
			"Material Transfer": "stock_transfer",
		}.get(purpose)
	return None


def general_form(phrase: str) -> str:
	"""The sentence without the names and numbers in it."""
	from iran_erp.commands.engine import _without_names

	words = tokens(_without_names(phrase))
	# "پنجاه میلیون", "۳ تا": amounts and counts change every time
	numbers = {i for n in find_numbers(words) for i in range(n.start, n.end)}
	return " ".join(w for i, w in enumerate(words) if i not in numbers and w != ",")


def learn(intent: str, phrase: str) -> bool:
	from iran_erp.commands.engine import INTENT_BY_NAME, get_matcher

	if intent not in INTENT_BY_NAME or INTENT_BY_NAME[intent].get("ai"):
		return False
	phrase = general_form(phrase or "")
	if len(phrase.split()) < MIN_WORDS or len(phrase) > 300 or yes_no(phrase) is not None:
		return False
	ranked = get_matcher().rank(phrase)
	if ranked and ranked[0][0] == intent and ranked[0][1] >= KNOWN_SCORE:
		return False
	name = LEARNED_PREFIX + INTENT_BY_NAME[intent]["title"]
	if frappe.db.exists("Iran Chat Command", name):
		doc = frappe.get_doc("Iran Chat Command", name)
	else:
		doc = frappe.new_doc("Iran Chat Command")
		doc.update(
			{
				"command_name": name,
				"action": "Built-in Command",
				"intent": intent,
				"learned": 1,
				"phrases": "",
			}
		)
	phrases = [p for p in (doc.phrases or "").splitlines() if p.strip()]
	if phrase in phrases:
		return False
	doc.phrases = "\n".join([*phrases, phrase][-MAX_PHRASES:])
	doc.save(ignore_permissions=True)
	return True


def unlearn(intent: str, phrase: str):
	"""Take a learned sentence back after the user said the answer it led to was wrong."""
	from iran_erp.commands.engine import INTENT_BY_NAME

	if intent not in INTENT_BY_NAME:
		return
	name = LEARNED_PREFIX + INTENT_BY_NAME[intent]["title"]
	if not frappe.db.exists("Iran Chat Command", name):
		return
	doc = frappe.get_doc("Iran Chat Command", name)
	phrase = general_form(phrase)
	phrases = [p for p in (doc.phrases or "").splitlines() if p.strip() and p != phrase]
	if not phrases:
		doc.delete(ignore_permissions=True)
	elif len(phrases) != len((doc.phrases or "").splitlines()):
		doc.phrases = "\n".join(phrases)
		doc.save(ignore_permissions=True)


def learn_from_ai(request, actions: list) -> bool:
	"""After the AI model finished a request: learn its wording if it did what one command does.
	True when the request was one command's work (learned now or already known)."""
	created = [(a.get("created"), a.get("name")) for a in actions or [] if a.get("created") and a.get("name")]
	intents = {_intent_for(doctype, name) for doctype, name in created}
	if len(intents) != 1 or None in intents:
		return False
	intent = intents.pop()
	# A short reply ("بله", a name) answered an earlier question: learn that question instead
	current = request
	for _step in range(LOOK_BACK + 1):
		if len(tokens(current.question or "")) > MIN_WORDS and not current.get("attachments"):
			learn(intent, current.question)
			return True
		if not current.previous_request:
			return True
		current = frappe.get_doc("Iran AI Request", current.previous_request)
	return True
