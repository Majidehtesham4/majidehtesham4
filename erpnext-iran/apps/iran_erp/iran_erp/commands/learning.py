"""Learn new ways of asking for a capability, so the next request worded the same way is understood
without an AI model. What is learned is the wording and where it leads, never the answer: figures
such as a balance or a stock level are read from the ERP again on every request.

An example (Iran Intent Example) holds the request without names and numbers, the capability and
its tool, the details read from it as the user said them, where it came from and how it was checked.
Examples come from
- the AI model reading a request the matcher was not sure of into a capability (understand.py),
- the AI assistant running a capability, or creating one kind of document a command creates,
- the user picking a command from the «which one did you mean?» list.

Every example starts as Proposed and teaches nothing until it is Approved:
1. evaluate() checks it against the ERP: the capability exists and has a tool, its details are found
   as records, the capability runs (one that reads, in a savepoint rolled back afterwards; one that
   makes or changes something is not run, only its details are checked), and no other capability
   claims the same wording.
2. A wording for a capability that only reads is approved once it passed and was confirmed: picked by
   the user, or read the same way by the AI model with confidence AUTO_CONFIDENCE again
   (AUTO_SEEN times). Wordings for drafts and changes, and anything that failed, wait for an
   administrator (Approve / Reject on the form or the list).
3. When the AI model was unsure, capabilities competed or none fits, the example is Needs Review
   with the reason; a «not right» from the user rejects the example behind the answer.
"""

import json
import re

import frappe
from frappe import _

from iran_erp.commands.text import find_numbers, tokens, yes_no

MIN_WORDS = 3
# Already understood this well: nothing to learn
KNOWN_SCORE = 0.8
# How far back a short follow-up ("بله", "علی") looks for the request it answered
LOOK_BACK = 3
# The AI model's confidence below which its reading is a question for an administrator
REVIEW_CONFIDENCE = 0.7
# Approved without an administrator: a read-only capability, seen this often with this confidence
AUTO_SEEN = 2
AUTO_CONFIDENCE = 0.85
# Another capability matching the wording this well competes with it
RIVAL_SCORE = 0.5
# Details never kept in an example
SECRET_TYPES = ("password", "username")

# Wordings learned before examples were reviewed, kept in Iran Chat Command
LEARNED_PREFIX = "آموخته: "


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




def _public(capability: str, parameters: dict | None) -> dict:
	"""The details worth keeping: as the user said them, without passwords and usernames."""
	from iran_erp.commands.engine import _slots

	secret = {slot for slot, kind, _r, _q in _slots(capability) if kind in SECRET_TYPES}
	out = {}
	for slot, value in (parameters or {}).items():
		if slot.startswith("_") or slot in secret or value in (None, "", [], {}):
			continue
		out[slot] = value if isinstance(value, (str, int, float)) else json.loads(json.dumps(value, default=str))
	return out


def _without_secrets(capability: str, phrase: str, parameters: dict | None) -> str:
	"""A request that gives a login's username or password is learned without them: the values said
	are taken out, and for such a capability every word in Latin letters too."""
	from iran_erp.commands.engine import _slots

	secret = {slot for slot, kind, _r, _q in _slots(capability) if kind in SECRET_TYPES} if capability else set()
	for slot in secret:
		value = (parameters or {}).get(slot)
		if isinstance(value, str) and value.strip():
			phrase = phrase.replace(value.strip(), " ")
	if secret:
		phrase = " ".join(w for w in phrase.split() if not re.search(r"[A-Za-z0-9]", w))
	return phrase


def _find(capability: str, phrase: str):
	return frappe.db.get_value("Iran Intent Example", {"capability": capability or "", "phrase": phrase})


def propose(
	capability: str | None,
	phrase: str,
	parameters: dict | None = None,
	source: str = "AI Interpreter",
	confidence: float | None = None,
	alternatives=(),
	request: str | None = None,
	review: str | None = None,
) -> str | None:
	"""Keep a wording and where it led as a proposed example, check it and approve it when the rules
	allow. review: why it needs an administrator (the AI model was unsure, capabilities compete, no
	capability fits). Returns the example's name, or None when there is nothing to learn."""
	from iran_erp.commands.engine import INTENT_BY_NAME

	if not frappe.db.table_exists("Iran Intent Example"):
		return None
	capability = capability or ""
	if capability and (capability not in INTENT_BY_NAME or INTENT_BY_NAME[capability].get("ai")):
		capability, review = "", review or _("The AI model named a capability the catalog does not have: {0}").format(capability)
	phrase = general_form(_without_secrets(capability, phrase or "", parameters))
	if len(phrase.split()) < MIN_WORDS or len(phrase) > 300 or yes_no(phrase) is not None:
		return None
	if capability and not review:
		from iran_erp.commands.engine import get_matcher

		ranked = get_matcher().rank(phrase)
		if ranked and ranked[0][0] == capability and ranked[0][1] >= KNOWN_SCORE:
			return None
	alternatives = [a for a in alternatives or () if a and a != capability]
	if confidence is not None and confidence < REVIEW_CONFIDENCE and not review:
		review = _("The AI model was not sure ({0:.0%}).").format(confidence)
	if alternatives and not review:
		review = _("Other capabilities may fit: {0}").format(", ".join(alternatives))
	if not capability and not review:
		review = _("No capability fits this request; a new tool may be needed.")

	name = _find(capability, phrase)
	if name:
		doc = frappe.get_doc("Iran Intent Example", name)
		if doc.status == "Rejected":
			return doc.name
		doc.times_seen = (doc.times_seen or 0) + 1
		if confidence is not None:
			doc.confidence = max(doc.confidence or 0, confidence)
		if source == "User Choice":
			doc.source = source
	else:
		doc = frappe.new_doc("Iran Intent Example")
		doc.update({"phrase": phrase, "capability": capability, "source": source, "confidence": confidence, "times_seen": 1})
	doc.parameters = json.dumps(_public(capability, parameters), ensure_ascii=False, default=str)
	doc.alternatives = ", ".join(alternatives)[:140]
	doc.last_request = request
	if review and doc.status != "Approved":
		doc.status = "Needs Review"
		doc.review_reason = review
	doc.flags.ignore_permissions = True
	doc.save()
	if capability and doc.status in ("Proposed", "Needs Review"):
		evaluate(doc)
		maybe_approve(doc)
	return doc.name


def evaluate(doc) -> bool:
	"""Check an example against the ERP; keeps Passed or Failed with what was found."""
	from iran_erp.commands import engine
	from iran_erp.commands import slots as slot_readers
	from iran_erp.commands.capabilities import ParameterProblem, kind_of, read_parameters, tool_of

	notes, ok = [], True
	capability = doc.capability
	if capability not in engine.INTENT_BY_NAME:
		doc.db_set({"evaluation": "Failed", "evaluation_notes": _("No such capability")})
		return False
	doc.capability_title = engine.INTENT_BY_NAME[capability]["title"]
	doc.tool = tool_of(capability)[:140]
	parameters = json.loads(doc.parameters or "{}")
	try:
		values = read_parameters(capability, parameters)
		notes.append(_("Details found in the ERP: {0}").format(", ".join(values) or "-"))
	except ParameterProblem as e:
		values = None
		ok = False
		notes.append(_("A detail is not on record or matches several: {0}").format(e))

	# The wording must not belong to another capability
	ranked = engine.get_matcher().rank(doc.phrase)
	rival = next((r for r in ranked if r[0] != capability and not r[0].startswith(("howto:", "recipe:", "custom:"))), None)
	mine = next((r for r in ranked if r[0] == capability), None)
	if rival and rival[1] >= RIVAL_SCORE and (not mine or rival[1] > mine[1]):
		ok = False
		notes.append(_("The wording already leads to {0} ({1:.2f})").format(rival[0], rival[1]))
	clash = frappe.db.get_value(
		"Iran Intent Example", {"phrase": doc.phrase, "status": "Approved", "capability": ("!=", capability)}, "capability"
	)
	if clash:
		ok = False
		notes.append(_("An approved example gives the same wording to {0}").format(clash))

	kind = kind_of(capability)
	if values is not None and kind == "read":
		# Run it for real, then undo whatever it touched
		frappe.db.savepoint("iran_learn_check")
		try:
			reply = engine._run(capability, dict(values), slot_readers.Message(doc.phrase, engine._keywords(capability)), False)
			if reply.get("error") or not reply.get("answer"):
				ok = False
				notes.append(_("The capability gave no answer"))
			else:
				waiting = (reply.get("state") or {}).get("waiting")
				notes.append(
					_("The capability ran and asks for {0}").format(waiting)
					if waiting
					else _("The capability ran: {0} link(s)").format(len(reply.get("actions") or []))
				)
		except Exception as e:
			ok = False
			notes.append(_("The capability failed: {0}").format(frappe.utils.strip_html(str(e))[:200]))
		finally:
			frappe.db.rollback(save_point="iran_learn_check")
			frappe.clear_last_message()
	elif values is not None:
		notes.append(_("Not run: it makes or changes records ({0}); only its details were checked").format(kind))
	doc.db_set(
		{
			"evaluation": "Passed" if ok else "Failed",
			"evaluation_notes": "\n".join(notes),
			"capability_title": doc.capability_title,
			"tool": doc.tool,
		}
	)
	return ok


def maybe_approve(doc) -> bool:
	from iran_erp.commands.capabilities import kind_of

	if doc.status != "Proposed" or doc.evaluation != "Passed" or kind_of(doc.capability) != "read":
		return False
	confirmed = doc.source == "User Choice" or (
		(doc.confidence or 0) >= AUTO_CONFIDENCE and (doc.times_seen or 0) >= AUTO_SEEN
	)
	if not confirmed:
		return False
	set_status(doc.name, "Approved")
	return True


def set_status(name: str, status: str, reason: str | None = None):
	from iran_erp.commands.engine import reset_matcher

	values = {"status": status}
	if reason:
		values["review_reason"] = reason
	frappe.db.set_value("Iran Intent Example", name, values)
	reset_matcher()


def approved_examples() -> list[dict]:
	if not frappe.db.table_exists("Iran Intent Example"):
		return []
	return frappe.get_all(
		"Iran Intent Example", filters={"status": "Approved", "capability": ("is", "set")}, fields=["capability", "phrase"]
	)


def learn(intent: str, phrase: str) -> bool:
	"""The user picked this command for this request from the «which one did you mean?» list."""
	return bool(propose(intent, phrase, source="User Choice"))


def unlearn(intent: str, phrase: str):
	"""The user said the answer was wrong: the example behind it is never used again, and a wording
	learned before examples were reviewed is taken back too."""
	from iran_erp.commands.engine import INTENT_BY_NAME

	if intent not in INTENT_BY_NAME:
		return
	phrase = general_form(_without_secrets(intent, phrase or "", None))
	if frappe.db.table_exists("Iran Intent Example"):
		name = _find(intent, phrase)
		if name:
			set_status(name, "Rejected", _("The user said the answer was wrong."))
	old = LEARNED_PREFIX + INTENT_BY_NAME[intent]["title"]
	if frappe.db.exists("Iran Chat Command", old):
		doc = frappe.get_doc("Iran Chat Command", old)
		phrases = [p for p in (doc.phrases or "").splitlines() if p.strip() and p != phrase]
		if not phrases:
			doc.delete(ignore_permissions=True)
		elif len(phrases) != len((doc.phrases or "").splitlines()):
			doc.phrases = "\n".join(phrases)
			doc.save(ignore_permissions=True)


def _capability_calls(run_messages) -> list[tuple[str, dict]]:
	"""The capabilities the AI assistant ran successfully, with the details it gave them."""
	results = {m.get("tool_call_id"): m.get("content") for m in run_messages or [] if m.get("role") == "tool"}
	calls = []
	for message in run_messages or []:
		for call in message.get("tool_calls") or []:
			function = call.get("function") or {}
			if function.get("name") != "run_capability":
				continue
			try:
				args = json.loads(function.get("arguments") or "{}")
				result = json.loads(results.get(call.get("id")) or "{}")
			except ValueError:
				continue
			if result.get("answer") and not result.get("error"):
				calls.append((args.get("capability"), args.get("parameters") or {}))
	return calls


def _asking_request(request):
	"""The request a short reply («بله», a name) answered, or the request itself."""
	current = request
	for _step in range(LOOK_BACK + 1):
		if len(tokens(current.question or "")) > MIN_WORDS and not current.get("attachments"):
			return current
		if not current.previous_request:
			return None
		current = frappe.get_doc("Iran AI Request", current.previous_request)
	return None


def learn_from_ai(request, actions: list, run_messages=()) -> bool:
	"""After the AI assistant finished a request: propose its wording for the capability it used.
	True when the request was one capability's work (so it is not also kept as a recipe)."""
	calls = _capability_calls(run_messages)
	if calls:
		capabilities = {c for c, _p in calls}
		asking = _asking_request(request)
		if asking:
			capability, parameters = calls[0]
			rivals = sorted(capabilities - {capability})
			propose(capability, asking.question, parameters, "AI Assistant", alternatives=rivals, request=request.name,
				review=_("The AI assistant used several capabilities for one request.") if rivals else None)
		return len(capabilities) == 1
	created = [(a.get("created"), a.get("name")) for a in actions or [] if a.get("created") and a.get("name")]
	intents = {_intent_for(doctype, name) for doctype, name in created}
	if len(intents) != 1 or None in intents:
		return False
	asking = _asking_request(request)
	if asking:
		propose(intents.pop(), asking.question, source="AI Assistant", request=request.name)
	return True
