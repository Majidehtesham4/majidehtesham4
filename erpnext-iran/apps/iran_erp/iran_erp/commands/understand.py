"""The AI model as the assistant's reader: it turns a request the matcher was not sure of into a
capability of the catalog and its details, and the capability then runs here on the ERP.

The model gets the catalog (each capability's id, what it does, its details, defaults and a few
ways of asking) and the request, and answers with JSON only: no tools, no figures, no answer text.
What it says is checked: the capability must exist, its details are read by the same readers as a
typed request (names become records), and the capability's own handler gives the answer and links.
So the user gets the same answer as for a request the matcher understood, from live ERP data, and
never has to ask for the AI model.

- The model is sure and one capability fits: it runs.
- The model is unsure, or names competing capabilities: the user is asked to choose among them, in
  one short question.
- The request needs reasoning, several steps, files or something no capability does: the AI
  assistant (ai/assistant.py) works on it, with every tool.

Every reading is proposed as a learning example (commands/learning.py); it teaches the matcher only
after it is checked and approved.
"""

import json
import re

import frappe
from frappe import _

from iran_erp.commands import engine
from iran_erp.commands import slots as slot_readers

# The model's confidence needed to run a capability without asking
CONFIDENT = 0.7
# Examples of each capability shown to the model
EXAMPLES_SHOWN = 3
# How long the model may take before the answer the matcher had is given instead
TIMEOUT = 25

PROMPT = """You read requests written to the assistant of ERP-VERON, an Iranian business system, and \
map each one to one capability of the catalog below. You do not answer the request and you never \
give figures: the capability you choose runs on the ERP and gives the answer.

Reply with one JSON object and nothing else:
{{"capability": "<id from the catalog, or null>",
  "parameters": {{"<parameter>": "<the words of the request for it, copied as written>"}},
  "confidence": <0 to 1, how sure you are that this capability is what the user wants>,
  "alternatives": ["<other ids that fit almost as well>"],
  "conversation": <true when the request needs reasoning, an explanation, several steps or tools at \
once, attached files, or nothing in the catalog does it; otherwise false>,
  "reason": "<a few words>"}}

Rules:
- Choose by what the user wants done or shown, not by single words: «اطلاعات سرمایه‌گذار X» asks \
for the investor's record, not for a login or an invoice; «فاکتورهای فروش رو بیار» lists invoices, \
it does not make one.
- Choose the capability that gives the shape of answer asked for: one particular record (a car by \
model, year and colour: car_search), a ranking («قدیمی‌ترین», «بیشترین زمان»: car_aging), a total \
per group («هر شعبه»: sales_by_branch), a count, or the whole list only when «همه» is said. A \
report with no subject is report_menu.
- Parameters: copy names, periods, amounts and other details exactly as the request writes them \
(Persian, with the user's spelling). Leave out what is not said; the capability's defaults apply. \
Write «همه» when the request asks for everyone. Never invent a value.
- A short message that only changes the previous request («همه», «امسال», «برای علی») keeps the \
previous request's capability, with the new detail.
- Never put a password or username you were not given into the parameters.
- If two capabilities fit, give the better one with a lower confidence and list the other in \
alternatives.

Catalog (id | what it does | parameters: name (type, * required) | defaults | ways of asking):
{catalog}"""


def catalog_text() -> str:
	from iran_erp.commands.capabilities import CAPABILITIES

	lines = []
	for intent in engine.INTENTS:
		meta = CAPABILITIES.get(intent["name"], {})
		parameters = ", ".join(
			f"{slot} ({kind}{', *' if required else ''})" for slot, kind, required, _q in intent.get("slots", [])
		)
		examples = " ؛ ".join(e for e in intent["examples"][:EXAMPLES_SHOWN])
		lines.append(
			f"{intent['name']} | {intent['title']} | {parameters or '-'} | {meta.get('defaults', '-')} | {examples}"
		)
	return "\n".join(lines)


def _parse(content: str) -> dict:
	"""The JSON object in the model's reply (it may wrap it in a code block or a sentence)."""
	match = re.search(r"\{.*\}", content or "", re.S)
	if not match:
		raise ValueError("no JSON in the reply")
	data = json.loads(match.group(0))
	capability = data.get("capability") or None
	try:
		confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
	except (TypeError, ValueError):
		confidence = 0.0
	return {
		"capability": capability if isinstance(capability, str) else None,
		"parameters": data.get("parameters") if isinstance(data.get("parameters"), dict) else {},
		"confidence": confidence,
		"alternatives": [a for a in data.get("alternatives") or [] if isinstance(a, str)][:3],
		"conversation": bool(data.get("conversation")),
		"reason": str(data.get("reason") or "")[:200],
	}


def interpret(question: str, previous: str | None = None, settings=None) -> dict:
	"""Ask the AI model which capability a request is for. Raises AIError when it cannot be reached."""
	from iran_erp.ai.openrouter import chat_completion, get_settings

	settings = settings or get_settings()
	settings = frappe._dict(settings, timeout=TIMEOUT)
	content = question if not previous else f"Previous request: {previous}\nThis request: {question}"
	response = chat_completion(
		settings,
		[{"role": "system", "content": PROMPT.format(catalog=catalog_text())}, {"role": "user", "content": content}],
	)
	message = (response.get("choices") or [{}])[0].get("message") or {}
	return {**_parse(message.get("content") or ""), "tokens": (response.get("usage") or {}).get("total_tokens") or 0}


def answer(question: str, state: dict | None, reading: dict, candidates=(), request: str | None = None) -> dict | None:
	"""The reply for a request the AI model read, run by the capability; None when the AI assistant
	should work on it (reasoning, several steps, nothing in the catalog)."""
	from iran_erp.commands.capabilities import ParameterProblem, read_parameters
	from iran_erp.commands.learning import propose

	capability = reading.get("capability")
	known = capability in engine.INTENT_BY_NAME
	alternatives = [a for a in reading.get("alternatives") or [] if a in engine.INTENT_BY_NAME and a != capability]
	if reading.get("conversation") or not known:
		# Nothing in the catalog does it: noted for an administrator, unless it is only conversation
		if not reading.get("conversation") or capability:
			propose(None, question, source="AI Interpreter", confidence=reading.get("confidence"), request=request,
				review=_("No capability fits: {0}").format(reading.get("reason") or capability or "-"))
		return None
	if engine.INTENT_BY_NAME[capability].get("ai"):
		return None

	# Unsure, or another capability fits as well: one short question with the choices
	if reading["confidence"] < CONFIDENT or alternatives:
		choices = [capability, *alternatives][:3]
		# The matcher's best guess too, when the model did not name it
		matcher_best = next((c for c, score in candidates or () if c in engine.INTENT_BY_NAME and score >= engine.UNSURE), None)
		if matcher_best and matcher_best not in choices and len(choices) < 3:
			choices.append(matcher_best)
		if len(choices) > 1:
			propose(capability, question, reading["parameters"], "AI Interpreter", reading["confidence"], alternatives, request)
			reply = engine._reply(
				_("Which one did you mean? Reply with its number.")
				+ "\n\n"
				+ engine._options_text([(c, engine._title(c)) for c in choices]),
				state={"choose": choices, "question": question},
				intent=capability,
				score=reading["confidence"],
			)
			reply["trace"] = {"understood_by": "AI Interpreter", "choices": choices, "reading": _reading(reading)}
			return reply

	values, problem = {}, None
	try:
		values = read_parameters(capability, reading["parameters"])
	except ParameterProblem as e:
		problem = e
		# The other details still count; the capability reads or asks for this one itself
		values = {}
		for slot, text in reading["parameters"].items():
			if slot == e.slot:
				continue
			try:
				values.update(read_parameters(capability, {slot: text}))
			except ParameterProblem:
				pass
		if e.options:
			reply = engine._ask(capability, values, e.slot, engine._slot_question(capability, e.slot) or _("Which one?"), e.options)
			reply["trace"] = {"understood_by": "AI Interpreter", "capability": capability, "reading": _reading(reading)}
			return reply

	message = slot_readers.Message(question, engine._keywords(capability))
	frappe.local.iran_cmd_last = None
	reply = engine._run(capability, values, message, ai_available=False)
	last = getattr(frappe.local, "iran_cmd_last", None)
	if last and not reply.get("state"):
		reply["state"] = {"last": last[0], "last_values": last[1]}
	reply["score"] = reading["confidence"]
	reply.setdefault("trace", {"capability": capability})
	reply["trace"].update(understood_by="AI Interpreter", reading=_reading(reading))
	if problem:
		reply["trace"]["not_found"] = str(problem)
	propose(capability, question, reading["parameters"], "AI Interpreter", reading["confidence"], alternatives, request)
	return reply


def _reading(reading: dict) -> dict:
	"""The model's reading as kept in the trace, without secrets."""
	parameters = {k: v for k, v in (reading.get("parameters") or {}).items() if k not in ("password", "username")}
	return {k: reading.get(k) for k in ("capability", "confidence", "alternatives", "conversation", "reason")} | {
		"parameters": parameters
	}
