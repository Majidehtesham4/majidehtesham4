"""Run a chat message as a command: pick the command, read its details, ask for what is missing.

handle() returns a dict with the answer and links, the conversation state to keep for the next
message (a question the user still has to answer), and "delegate": True when the message should go
to the AI model instead.
"""

import importlib
import json

import frappe
from frappe import _

from iran_erp.commands import recipes
from iran_erp.commands import slots as slot_readers
from iran_erp.commands.catalog import DOCTYPES, INTENTS, REPORTS
from iran_erp.commands.matcher import Matcher, features
from iran_erp.commands.text import is_cancel, normalize, tokens, yes_no

# Scores are cosine similarities with the closest sample sentence
SURE = 0.5
UNSURE = 0.3
# The best command has to beat the second best by this much to be taken without asking
MARGIN = 0.04
# Messages this long usually ask for several things at once: better for the AI model
LONG_MESSAGE = 40
# With an AI model available, commands below this score go to it instead
SURE_WITH_AI = 0.6
# Questions that ask for reasoning rather than a figure or a document
ANALYSIS_WORDS = {
	"چرا",
	"تحلیل",
	"مقایسه",
	"پیشنهاد",
	"بررسی",
	"توضیح",
	"چطور",
	"چگونه",
	"پیشبینی",
	"علت",
	"دلیل",
	"تفاوت",
	"روند",
}

INTENT_BY_NAME = {intent["name"]: intent for intent in INTENTS}
# Commands that only open a page; a command that answers the question wins over them on a near tie
NAVIGATION = {"open_list", "new_document", "open_report"}
_cache = {}


class NeedSlot(Exception):
	"""A handler needs one more detail from the user."""

	def __init__(self, slot: str, question: str, options=None):
		super().__init__(question)
		self.slot = slot
		self.question = question
		self.options = options or []


class NeedConfirm(Exception):
	"""A handler is about to do something that cannot be undone and wants a yes first."""

	def __init__(self, summary: str):
		super().__init__(summary)
		self.summary = summary


class Delegate(Exception):
	"""A handler found the request too complex: let the AI model do it."""


class Context:
	def __init__(self, intent, values, message, confirmed=False, ai_available=False):
		self.intent = intent
		self.values = values
		self.message = message
		self.confirmed = confirmed
		self.ai_available = ai_available

	def get(self, slot, default=None):
		value = self.values.get(slot)
		return default if value in (None, "", []) else value


def _generated_samples():
	"""Sample sentences made from the Persian names of document types and reports."""
	samples = []
	for doctype, names in DOCTYPES.items():
		for name in names:
			for template in ("لیست {}", "فهرست {}", "{}", "{} رو باز کن", "برو به {}", "صفحه {}"):
				samples.append(("open_list", template.format(name), {"doctype": doctype, "_generated": True}))
			for template in ("{} جدید", "فرم {} جدید", "یک {} جدید باز کن", "ایجاد {}"):
				samples.append(
					("new_document", template.format(name), {"doctype": doctype, "_generated": True})
				)
	for report, names in REPORTS.items():
		for name in names:
			for template in ("گزارش {}", "{}", "{} رو باز کن", "نمایش {}"):
				samples.append(("open_report", template.format(name), {"report": report, "_generated": True}))
	return samples


def custom_commands() -> list[dict]:
	if not frappe.db.table_exists("Iran Chat Command"):
		return []
	return frappe.get_all(
		"Iran Chat Command",
		filters={"enabled": 1},
		fields=["name", "command_name", "phrases", "action", "target", "filters", "reply", "intent"],
	)


def learned_recipes() -> list[dict]:
	if not frappe.db.table_exists("Iran Learned Recipe"):
		return []
	return frappe.get_all("Iran Learned Recipe", filters={"enabled": 1}, fields=["name", "phrases"])


def get_matcher() -> Matcher:
	version = frappe.cache.get_value("iran_cmd_version") or 0
	if _cache.get("version") != version or "matcher" not in _cache:
		samples = [(intent["name"], example, {}) for intent in INTENTS for example in intent["examples"]]
		samples += _generated_samples()
		for command in custom_commands():
			intent = command.intent if command.action == "Built-in Command" else f"custom:{command.name}"
			for phrase in (command.phrases or "").splitlines():
				if phrase.strip():
					samples.append((intent, phrase.strip(), {}))
		for recipe in learned_recipes():
			for phrase in (recipe.phrases or "").splitlines():
				if phrase.strip():
					samples.append((f"recipe:{recipe.name}", phrase.strip(), {}))
		_cache.update(matcher=Matcher(samples), version=version)
	return _cache["matcher"]


def reset_matcher(*args, **kwargs):
	"""Called when custom commands or learned recipes change."""
	frappe.cache.set_value("iran_cmd_version", frappe.generate_hash(length=8))


def _keywords(intent_name: str) -> set[str]:
	"""The stems of the words the command's own samples use; they are not names or details."""
	from iran_erp.commands.matcher import PLACEHOLDER
	from iran_erp.commands.text import stem

	if intent_name not in _cache.setdefault("keywords", {}):
		words = set()
		for example in INTENT_BY_NAME.get(intent_name, {}).get("examples", []):
			words |= {stem(w) for w in tokens(PLACEHOLDER.sub(" ", example)) if not w.isdigit()}
		_cache["keywords"][intent_name] = words
	return _cache["keywords"][intent_name]


def _reply(answer, actions=None, state=None, intent=None, score=None, **extra):
	return {
		"answer": answer,
		"actions": actions or [],
		"state": state,
		"intent": intent,
		"score": score,
		**extra,
	}


def _options_text(options) -> str:
	return "\n".join(f"{i}. {label}" for i, (_value, label) in enumerate(options, 1))


def handle(question: str, state: dict | None = None, ai_available: bool = False) -> dict:
	question = (question or "").strip()
	state = state or {}

	if state and is_cancel(question):
		return _reply(_("Cancelled."))
	if state.get("choose"):
		chosen = _pick(question, [(name, name) for name in state["choose"]])
		if chosen:
			# The user's choice teaches the wording, so the same request is not asked about again
			from iran_erp.commands.learning import learn

			learn(chosen, state.get("question") or "")
			return _run(
				chosen,
				dict(state.get("values") or {}),
				slot_readers.Message(state.get("question") or question, _keywords(chosen)),
				ai_available,
			)
	if state.get("intent"):
		follow_up = _continue(question, state, ai_available)
		if follow_up:
			return follow_up

	words = tokens(question)
	if ai_available and (len(words) > LONG_MESSAGE or set(words) & ANALYSIS_WORDS):
		return _reply(None, delegate=True)

	ranked = get_matcher().rank(_without_names(question))
	if not ranked or ranked[0][1] < UNSURE:
		return _not_understood(question, ranked, ai_available)
	ranked = _prefer_specific(ranked)
	ranked = _prefer_fitting(question, ranked)
	best, score, values = ranked[0]
	runner_up = next((r for r in ranked[1:] if r[0] != best and r[0] not in NAVIGATION), None)
	close_call = runner_up and best not in NAVIGATION and score - runner_up[1] < MARGIN
	if score < (SURE_WITH_AI if ai_available else SURE) or close_call:
		if ai_available:
			return _reply(None, delegate=True, intent=best, score=score)
		choices = [r[0] for r in ranked[:3] if r[1] >= UNSURE]
		return _reply(
			_("Which one did you mean? Reply with its number.")
			+ "\n\n"
			+ _options_text([(c, _title(c)) for c in choices]),
			state={"choose": choices, "question": question},
			intent=best,
			score=score,
		)

	# A learned recipe repeats what was done once; with the AI model at hand, only for a close match
	if best.startswith("recipe:") and ai_available and score < recipes.MIN_SCORE:
		return _reply(None, delegate=True, intent=best, score=score)
	intent = INTENT_BY_NAME.get(best)
	if intent and intent.get("ai") and ai_available:
		return _reply(None, delegate=True, intent=best, score=score)
	values = {k: v for k, v in values.items() if not k.startswith("_")}
	result = _run(best, values, slot_readers.Message(question, _keywords(best)), ai_available)
	result["score"] = score
	return result


def _without_names(question: str) -> str:
	"""The message without the customers, suppliers and items it names, which only confuse matching:
	"پیش فاکتور برای شرکت نمونه" is about a quotation, not about the list of companies."""
	from iran_erp.commands import entities
	from iran_erp.commands.text import pieces

	words = [w for w, _ in pieces(question)]
	skip = set()
	for kind in ("customer", "supplier", "item"):
		for _attempt in range(3):
			found = entities.find(kind, words, skip)
			# Only whole names or several words: one common word may just be part of the request
			if not (found or found.options) or found.score < 15:
				break
			skip |= found.used
	if not skip:
		return question
	return " ".join(w for i, w in enumerate(words) if i not in skip)


def _prefer_specific(ranked):
	"""On a near tie between opening a page and answering, answer: "سود و زیان امسال" gives the figures."""
	if len(ranked) > 1 and ranked[0][0] in NAVIGATION:
		specific = next((r for r in ranked[1:] if r[0] not in NAVIGATION), None)
		if specific and ranked[0][1] - specific[1] < MARGIN * 2:
			ranked = [specific] + [r for r in ranked if r is not specific]
	return ranked


# Near ties are settled by the details the message gives: a command loses this much for each
# required detail missing, and gains this much for each optional one found
MISSING_PENALTY = 0.08
FOUND_BONUS = 0.05


def _detail_score(intent_name: str, question: str) -> float:
	message = slot_readers.Message(question, _keywords(intent_name))
	order = {t: i for i, t in enumerate(slot_readers.ORDER)}
	adjustment = 0.0
	for slot, slot_type, required, _question in sorted(
		_slots(intent_name), key=lambda s: order.get(s[1], 99)
	):
		# Free text takes whatever is left, so it tells nothing
		if slot_type in ("name", "text"):
			continue
		try:
			value = slot_readers.extract(slot_type, message, slot)
		except slot_readers.Ambiguous:
			value = True
		if isinstance(value, dict) and "lines" in value:
			value = value["lines"]
		found = value not in (None, "", [])
		if required and not found:
			adjustment -= MISSING_PENALTY
		elif found and not required:
			adjustment += FOUND_BONUS
	return adjustment


def _prefer_fitting(question, ranked):
	"""Re-score near ties by the details the message gives: "فروش این ماه" is the sales total, not
	the sales of an item that was not named; "سرنخ جدید علی ۰۹۱۲..." creates a lead, it does not list them."""
	best_score = ranked[0][1]
	adjusted = []
	for intent, score, values in ranked:
		if intent not in NAVIGATION and best_score - score < MARGIN * 3:
			score = round(score + _detail_score(intent, question), 3)
		adjusted.append((intent, score, values))
	return sorted(adjusted, key=lambda r: r[1], reverse=True)


def _title(intent_name: str) -> str:
	if intent_name.startswith("recipe:"):
		return frappe.db.get_value("Iran Learned Recipe", intent_name[7:], "title") or intent_name
	if intent_name.startswith("custom:"):
		return frappe.db.get_value("Iran Chat Command", intent_name[7:], "command_name") or intent_name
	return INTENT_BY_NAME[intent_name]["title"]


def _pick(text: str, options: list) -> str | None:
	"""The option a reply chooses, by its number or by its name."""
	words = tokens(text)
	if len(words) == 1 and words[0].isdigit() and 1 <= int(words[0]) <= len(options):
		return options[int(words[0]) - 1][0]
	normalized = normalize(text)
	for value, label in options:
		if normalized and (normalized == normalize(label) or normalized in normalize(label)):
			return value
	return None


def _not_understood(question, ranked, ai_available):
	if ai_available:
		return _reply(None, delegate=True)
	suggestions = [r[0] for r in ranked[:3] if r[1] >= 0.15]
	text = _("I did not understand this request.")
	if suggestions:
		text += (
			" " + _("Did you mean one of these?") + "\n\n" + "\n".join(f"- {_title(s)}" for s in suggestions)
		)
	text += "\n\n" + _("Write «help» to see what I can do.")
	return _reply(text, intent=None, score=ranked[0][1] if ranked else 0, unrecognized=True)


def _continue(question, state, ai_available):
	"""A reply to a question the previous message asked, or None when it is a new request."""
	name = state["intent"]
	values = dict(state.get("values") or {})
	message = slot_readers.Message(question)
	if state.get("confirm"):
		answer = yes_no(question)
		if answer is None:
			return None
		if not answer:
			return _reply(_("Cancelled. Nothing was changed."))
		return _run(name, values, message, ai_available, confirmed=True)

	waiting = state.get("waiting")
	if name.startswith("recipe:") and waiting:
		# The recipe reads what it still needs from the reply itself
		# A reply that is only a name is the answer; a full new request starts over
		rest = _without_names(question)
		ranked = get_matcher().rank(rest) if rest.strip() else []
		if not (ranked and ranked[0][1] >= SURE and ranked[0][0] != name):
			return _run(name, values, message, ai_available)
		return None
	if state.get("options"):
		chosen = _pick(question, state["options"])
		if chosen:
			values[waiting] = chosen
			return _run(name, values, message, ai_available)
	if waiting:
		slot_type = _slot_type(name, waiting)
		value = None
		if slot_type in ("name", "text"):
			value = question
		else:
			try:
				value = slot_readers.extract(slot_type, message, waiting)
			except slot_readers.Ambiguous as e:
				return _ask(name, values, waiting, _slot_question(name, waiting), e.options)
		if value not in (None, ""):
			values[waiting] = value
			return _run(name, values, message, ai_available)
	# A plain "no" instead of an answer drops the request
	if yes_no(question) is False:
		return _reply(_("Cancelled. Nothing was changed."))
	# Not an answer to the question; a strong match for another command starts over
	ranked = get_matcher().rank(question)
	if ranked and ranked[0][1] >= SURE:
		return None
	return _ask(name, values, waiting, _slot_question(name, waiting), state.get("options"), again=True)


def _slots(intent_name):
	intent = INTENT_BY_NAME.get(intent_name) or {}
	return intent.get("slots", [])


def _slot_type(intent_name, slot):
	return next((s[1] for s in _slots(intent_name) if s[0] == slot), slot)


def _slot_question(intent_name, slot):
	return next((s[3] for s in _slots(intent_name) if s[0] == slot), "") or _("Please give more detail.")


def _ask(intent_name, values, slot, question, options=None, again=False):
	text = question
	if again:
		text = _("I could not read that.") + " " + question
	if options:
		text += "\n\n" + _options_text(options) + "\n\n" + _("Reply with the number.")
	state = {"intent": intent_name, "values": values, "waiting": slot, "options": options or None}
	return _reply(text, state=state, intent=intent_name)


def _run(intent_name, values, message, ai_available, confirmed=False):
	"""Read the slots still missing from the message, then run the command's handler."""
	if intent_name.startswith("custom:"):
		from iran_erp.commands.handlers import custom

		return _reply(**custom.run(intent_name[7:], message), intent=intent_name)
	if intent_name.startswith("recipe:"):
		return _run_recipe(intent_name, values, message, ai_available, confirmed)
	intent = INTENT_BY_NAME[intent_name]
	slot_list = intent.get("slots", [])
	order = {t: i for i, t in enumerate(slot_readers.ORDER)}
	for slot, slot_type, _required, _question in sorted(slot_list, key=lambda s: order.get(s[1], 99)):
		if values.get(slot) not in (None, ""):
			continue
		try:
			value = slot_readers.extract(slot_type, message, slot)
		except slot_readers.Ambiguous as e:
			return _ask(
				intent_name, values, slot, _slot_question(intent_name, slot) or _("Which one?"), e.options
			)
		if value not in (None, ""):
			values[slot] = value

	items = values.get("items")
	if isinstance(items, dict) and items.get("unknown"):
		if ai_available:
			return _reply(None, delegate=True, intent=intent_name)
		values.pop("items")
		return _ask(
			intent_name,
			values,
			"items",
			_(
				"These items were not found: {0}. Write the items again with their exact names, or define them first."
			).format("، ".join(items["unknown"])),
		)

	for slot, _type, required, question in slot_list:
		if required and values.get(slot) in (None, ""):
			return _ask(intent_name, values, slot, question)

	module, function = intent["handler"].rsplit(".", 1)
	handler = getattr(importlib.import_module(f"iran_erp.commands.handlers.{module}"), function)
	context = Context(intent_name, values, message, confirmed=confirmed, ai_available=ai_available)
	try:
		result = handler(context)
	except NeedSlot as e:
		return _ask(intent_name, values, e.slot, e.question, e.options)
	except NeedConfirm as e:
		return _reply(
			e.summary + "\n\n" + _("Shall I go ahead? (yes / no)"),
			state={"intent": intent_name, "values": values, "confirm": True},
			intent=intent_name,
		)
	except Delegate:
		if ai_available:
			return _reply(None, delegate=True, intent=intent_name)
		raise
	except frappe.PermissionError:
		frappe.clear_last_message()
		return _reply(_("You do not have permission for this."), intent=intent_name)
	if isinstance(result, str):
		result = {"answer": result}
	return _reply(intent=intent_name, **result)


def _run_recipe(intent_name, values, message, ai_available, confirmed):
	try:
		result = recipes.run(intent_name[7:], message, values, confirmed=confirmed)
	except NeedSlot as e:
		return _ask(intent_name, values, e.slot, e.question, e.options)
	except NeedConfirm as e:
		return _reply(
			e.summary + "\n\n" + _("Shall I go ahead? (yes / no)"),
			state={"intent": intent_name, "values": values, "confirm": True},
			intent=intent_name,
		)
	except frappe.PermissionError:
		frappe.clear_last_message()
		return _reply(_("You do not have permission for this."), intent=intent_name)
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return (
			_reply(None, delegate=True, intent=intent_name)
			if ai_available
			else _not_understood(message.text, [], False)
		)
	if result.pop("delegate_on_error", False) and ai_available:
		return _reply(None, delegate=True, intent=intent_name)
	return _reply(intent=intent_name, **result)


def _waiting_type(state) -> str | None:
	name, waiting = state.get("intent") or "", state.get("waiting")
	if not waiting:
		return None
	if name.startswith("recipe:"):
		slots = json.loads(frappe.db.get_value("Iran Learned Recipe", name[7:], "slots") or "{}")
		return (slots.get(waiting) or {}).get("type")
	return _slot_type(name, waiting)


def quick_replies(state: dict | None) -> dict:
	"""Buttons for answering the question a reply asked: yes/no, the numbered options, a few
	common answers, or a list to pick a customer, item, ... from. Each reply is sent as typed text."""
	from iran_erp.commands import entities

	if not state:
		return {}
	replies, pick = [], None
	if state.get("confirm"):
		replies = [{"label": "بله، انجام بده", "text": "بله"}, {"label": "نه", "text": "نه"}]
	elif state.get("choose"):
		replies = [{"label": _title(c), "text": str(i)} for i, c in enumerate(state["choose"], 1)]
	elif state.get("options"):
		replies = [{"label": label, "text": str(i)} for i, (_v, label) in enumerate(state["options"], 1)]
	else:
		kind = _waiting_type(state)
		if kind == "vat":
			replies = [
				{"label": "بله، با ارزش افزوده", "text": "بله"},
				{"label": "بدون ارزش افزوده", "text": "خیر"},
			]
		elif kind == "payment_mode":
			replies = [{"label": "نقدی", "text": "نقدی"}, {"label": "واریز به حساب", "text": "واریز به حساب"}]
		elif kind == "period":
			replies = [{"label": t, "text": t} for t in ("امروز", "این ماه", "ماه قبل", "امسال")]
		elif kind == "date":
			replies = [{"label": t, "text": t} for t in ("امروز", "فردا", "پس‌فردا")]
		elif kind in entities.SOURCES:
			doctype, _fields, filters, _label = entities.SOURCES[kind]
			pick = {"doctype": doctype, "filters": filters}
		elif kind in ("party", "party_or_account"):
			pick = {"doctype": "Customer", "filters": {"disabled": 0}}
	replies.append({"label": _("Cancel"), "text": "انصراف", "cancel": True})
	return {"replies": replies, "pick": pick}


def describe() -> list[dict]:
	"""The catalog for the help page and the README."""
	return [
		{
			"group": intent["group"],
			"name": intent["name"],
			"title": intent["title"],
			"example": intent["examples"][0],
		}
		for intent in INTENTS
	]


def debug(question: str) -> str:
	"""Scores and slots for a message, for tuning the samples: bench execute iran_erp.commands.engine.debug"""
	ranked = get_matcher().rank(question)
	return json.dumps({"features": len(features(question)), "ranked": ranked}, ensure_ascii=False, indent=1)
