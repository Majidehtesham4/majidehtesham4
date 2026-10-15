"""Learned recipes: what the AI model did once, done again without it.

When the AI model handles a request that no built-in command covers, the tool calls it made are kept
as a recipe. The customers, items, numbers, dates and periods of the user's message that appear in
those calls become placeholders; the rest stays as it was. The sentence (without names and numbers)
is added to the command matcher, so the next request worded the same way runs the recipe: its
details are read from the new message, put in place of the placeholders, and the same tools run,
with no AI model involved. Recipes that create documents ask the user first. Each AI-handled
request can teach one more, so the share of requests that need the AI model keeps shrinking.

Recipes live in Iran Learned Recipe, where an administrator can review, edit, add wordings or
switch them off; a «not right» from the user switches one off too.
"""

import copy
import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from iran_erp.commands import entities
from iran_erp.commands.text import find_date, find_mobile, find_numbers, find_period, pieces, tokens

# Tools whose calls can be replayed, and the ones among them that create or change documents
READ_TOOLS = {"search_documents", "run_report", "get_document"}
WRITE_TOOLS = {
	"create_draft_document",
	"create_items",
	"create_customer",
	"create_sales_invoice_draft",
	"create_purchase_invoice_draft",
}
# Entity kinds looked for in the message, most specific first
KINDS = ("customer", "supplier", "item", "bank_account", "warehouse", "project", "employee", "cash_account")
QUESTIONS = {
	"customer": "کدام مشتری؟",
	"supplier": "کدام تأمین‌کننده؟",
	"item": "کدام کالا؟",
	"bank_account": "کدام حساب بانکی؟",
	"warehouse": "کدام انبار؟",
	"project": "کدام پروژه؟",
	"employee": "کدام کارمند؟",
	"cash_account": "کدام حساب؟",
	"number": "چه مبلغ یا عددی؟",
	"date": "چه تاریخی؟",
	"mobile": "شماره‌ی موبایل؟",
}
LABELS = {
	"customer": "مشتری",
	"supplier": "تأمین‌کننده",
	"item": "کالا",
	"bank_account": "حساب بانکی",
	"warehouse": "انبار",
	"project": "پروژه",
	"employee": "کارمند",
	"cash_account": "حساب",
	"number": "مبلغ / عدد",
	"date": "تاریخ",
	"period": "بازه",
	"mobile": "موبایل",
}
PLACEHOLDER = re.compile(r"\{\{(\w+(?:\.\w+)?)\}\}")
MIN_SCORE = 0.75
MAX_FAILURES = 2


# ---------------------------------------------------------------- learning


def _effect_steps(messages: list) -> list[dict]:
	"""The tool calls of one AI run that did something, in order, without the ones that failed."""
	results = {m.get("tool_call_id"): m.get("content") for m in messages if m.get("role") == "tool"}
	steps = []
	for message in messages:
		for call in message.get("tool_calls") or []:
			function = call.get("function") or {}
			name = function.get("name")
			if name not in READ_TOOLS | WRITE_TOOLS:
				continue
			try:
				args = json.loads(function.get("arguments") or "{}")
				result = json.loads(results.get(call.get("id")) or "{}")
			except ValueError:
				continue
			if not isinstance(result, dict) or result.get("error"):
				continue
			# A purchase invoice read off an attached file cannot be done again without the file
			if args.get("file_url"):
				return []
			steps.append({"tool": name, "args": args})
	return steps


def _details(text: str) -> dict:
	"""What a message names: records by kind, numbers, a period, a date, a mobile number."""
	words = [w for w, _original in pieces(text)]
	found = {"entities": [], "numbers": [], "period": None, "date": None, "mobile": find_mobile(text)}
	skip = set()
	for kind in KINDS:
		for _attempt in range(3):
			match = entities.find(kind, words, skip)
			if not match or match.score < 15:
				break
			label = frappe.db.get_value(entities.SOURCES[kind][0], match.name, entities.SOURCES[kind][3])
			found["entities"].append({"kind": kind, "name": match.name, "label": label or match.name})
			skip |= match.used
	period, label = find_period(words)
	if period:
		found["period"] = {"from": str(period[0]), "to": str(period[1]), "label": label}
	date, _used = find_date(words)
	if date:
		found["date"] = str(date)
	for number in find_numbers(words):
		if not set(range(number.start, number.end)) & skip:
			found["numbers"].append(number.value)
	return found


def _dynamic_dates() -> dict[str, str]:
	"""Dates the AI model may have filled in by itself: they move with the calendar on replay."""
	import jdatetime

	today = getdate(nowdate())
	jtoday = jdatetime.date.fromgregorian(date=today)
	return {
		"today": str(today),
		"month_start": str(jdatetime.date(jtoday.year, jtoday.month, 1).togregorian()),
		"year_start": str(jdatetime.date(jtoday.year, 1, 1).togregorian()),
		"yesterday": str(add_days(today, -1)),
	}


def _template(args, details: dict, slots: dict):
	"""The arguments with the message's details replaced by {{placeholders}}; slots collects them."""
	dynamic = {value: key for key, value in _dynamic_dates().items()}

	def slot_for_entity(entity, index):
		key = entity["kind"] if index == 0 else f"{entity['kind']}_{index + 1}"
		slots[key] = {"type": entity["kind"], "sample": entity["label"], "index": index}
		return key

	def replace_text(value: str):
		for entity in details["entities"]:
			same_kind = [e for e in details["entities"] if e["kind"] == entity["kind"]]
			index = same_kind.index(entity)
			for text in {entity["name"], entity["label"]}:
				if text and text in value:
					value = value.replace(text, "{{" + slot_for_entity(entity, index) + "}}")
		period = details.get("period")
		if period:
			for part in ("from", "to"):
				if value == period[part]:
					slots["period"] = {"type": "period", "sample": period["label"]}
					return "{{period." + part + "}}"
		if details.get("date") and value == details["date"]:
			slots["date"] = {"type": "date", "sample": details["date"]}
			return "{{date}}"
		if details.get("mobile") and value == details["mobile"]:
			slots["mobile"] = {"type": "mobile", "sample": value}
			return "{{mobile}}"
		if value in dynamic:
			return "{{" + dynamic[value] + "}}"
		return value

	def walk(value):
		if isinstance(value, dict):
			return {k: walk(v) for k, v in value.items()}
		if isinstance(value, list):
			return [walk(v) for v in value]
		if isinstance(value, str):
			return replace_text(value)
		if isinstance(value, int | float) and not isinstance(value, bool):
			for index, number in enumerate(details["numbers"]):
				if float(value) == float(number) or float(value) == float(number) * 10:
					key = f"number_{index + 1}"
					slots[key] = {"type": "number", "sample": number, "index": index}
					return {"$slot": key, "toman": float(value) == float(number) * 10 and value != number}
		return value

	return walk(copy.deepcopy(args))


def learn_recipe(request, messages: list, question: str) -> str | None:
	"""Keep the AI model's tool calls for this request as a recipe; returns its name."""
	from iran_erp.commands.learning import general_form

	steps = _effect_steps(messages)
	if not steps or len(steps) > 6:
		return None
	phrase = general_form(question or "")
	if len(phrase.split()) < 3:
		return None
	details = _details(question)
	slots = {}
	templates = [{"tool": s["tool"], "args": _template(s["args"], details, slots)} for s in steps]
	signature = json.dumps(templates, ensure_ascii=False, sort_keys=True)
	writes = any(s["tool"] in WRITE_TOOLS for s in steps)

	for existing in frappe.get_all("Iran Learned Recipe", fields=["name", "steps", "phrases"]):
		if json.dumps(json.loads(existing.steps or "[]"), ensure_ascii=False, sort_keys=True) == signature:
			phrases = [p for p in (existing.phrases or "").splitlines() if p.strip()]
			if phrase not in phrases:
				doc = frappe.get_doc("Iran Learned Recipe", existing.name)
				doc.phrases = "\n".join([*phrases, phrase][-100:])
				doc.flags.ignore_permissions = True
				doc.save()
			return existing.name

	doc = frappe.get_doc(
		{
			"doctype": "Iran Learned Recipe",
			"title": question[:140],
			"phrases": phrase,
			"steps": json.dumps(templates, ensure_ascii=False, indent=1),
			"slots": json.dumps(slots, ensure_ascii=False, indent=1),
			"writes": int(writes),
			"learned_from": request.name,
			"enabled": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------- replay


def _fill(template, values: dict):
	def text(value: str):
		def repl(match):
			key = match.group(1)
			if "." in key:
				base, part = key.split(".", 1)
				return str((values.get(base) or {}).get(part, ""))
			return str(values.get(key, ""))

		return PLACEHOLDER.sub(repl, value)

	if isinstance(template, dict):
		if "$slot" in template:
			return values.get(template["$slot"])
		return {k: _fill(v, values) for k, v in template.items()}
	if isinstance(template, list):
		return [_fill(v, values) for v in template]
	if isinstance(template, str):
		return text(template)
	return template


def _read_values(slots: dict, message_text: str, known: dict) -> tuple[dict, str | None]:
	"""Values for the recipe's placeholders from a new message; the first missing one's name."""
	values = dict(_dynamic_dates())
	values.update(known)
	details = _details(message_text)
	by_kind = {}
	for entity in details["entities"]:
		by_kind.setdefault(entity["kind"], []).append(entity)
	for key, slot in slots.items():
		if key in values:
			continue
		kind = slot["type"]
		if kind in KINDS:
			found = by_kind.get(kind) or []
			index = slot.get("index", 0)
			if index < len(found):
				values[key] = found[index]["name"]
			else:
				return values, key
		elif kind == "period":
			period = details["period"]
			if not period:
				# The same span as the first time, counted from today: "این ماه" is this month again
				span, _label = find_period(tokens(slot.get("sample") or ""))
				period = {"from": str(span[0]), "to": str(span[1])} if span else None
			if not period:
				return values, key
			values[key] = period
		elif kind == "date":
			if not details["date"]:
				return values, key
			values[key] = details["date"]
		elif kind == "mobile":
			if not details["mobile"]:
				return values, key
			values[key] = details["mobile"]
		elif kind == "number":
			index = slot.get("index", 0)
			if index < len(details["numbers"]):
				values[key] = details["numbers"][index]
			else:
				return values, key
	return values, None


def _toman_slots(template, found=None) -> set[str]:
	"""Amounts said in toman that the AI model turned into rials the first time."""
	found = set() if found is None else found
	if isinstance(template, dict):
		if "$slot" in template:
			if template.get("toman"):
				found.add(template["$slot"])
			return found
		for v in template.values():
			_toman_slots(v, found)
	elif isinstance(template, list):
		for v in template:
			_toman_slots(v, found)
	return found


def _summary(steps) -> str:
	labels = {
		"create_draft_document": lambda a: _("a draft {0}").format(_(a.get("doctype") or "")),
		"create_items": lambda a: _("{0} items").format(len(a.get("items") or [])),
		"create_customer": lambda a: _("customer {0}").format(a.get("customer_name") or ""),
		"create_sales_invoice_draft": lambda a: _("a draft sales invoice for {0}").format(
			a.get("customer") or ""
		),
		"create_purchase_invoice_draft": lambda a: _("a draft purchase invoice from {0}").format(
			a.get("supplier") or a.get("supplier_name") or ""
		),
	}
	parts = [labels[s["tool"]](s["args"]) for s in steps if s["tool"] in labels]
	return "، ".join(parts)


def _details_text(slots: dict, values: dict) -> str:
	"""The details read from the message, so the user can check them before saying yes."""
	from iran_erp.commands.handlers import jdate, number

	lines = []
	for key, slot in slots.items():
		value = values.get(key)
		if value in (None, ""):
			continue
		kind = slot["type"]
		if kind == "number":
			value = number(value)
		elif kind == "date":
			value = jdate(value)
		elif kind == "period":
			value = f"{jdate(value.get('from'))} – {jdate(value.get('to'))}"
		elif kind in entities.SOURCES:
			value = frappe.db.get_value(entities.SOURCES[kind][0], value, entities.SOURCES[kind][3]) or value
		lines.append(f"- {LABELS.get(kind, kind)}: {value}")
	return ("\n\n" + "\n".join(lines)) if lines else ""


def _table(columns: list[str], rows: list[list], labels: dict | None = None) -> str:
	from iran_erp.commands.handlers import table

	headers = [labels.get(c, c) if labels else c for c in columns]
	return table(headers, rows)


DATE_WITH_JALALI = re.compile(r"^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})? \((.+)\)$")


def _format_value(value):
	from iran_erp.commands.handlers import number

	if isinstance(value, float | int) and not isinstance(value, bool):
		return number(value)
	if isinstance(value, str) and DATE_WITH_JALALI.match(value):
		# "2026-10-13 (۱۴۰۵/۰۷/۲۱)": the user reads the Jalali date
		return DATE_WITH_JALALI.match(value).group(1)
	if isinstance(value, dict | list):
		return json.dumps(value, ensure_ascii=False)[:60]
	return str(value if value is not None else "")[:80]


def _render(tool: str, args: dict, result) -> tuple[str, list]:
	"""A readable answer for one tool's result, and links to anything it made."""
	from iran_erp.commands.handlers import doc_link, link

	actions = []
	if not isinstance(result, dict):
		return "", actions
	if result.get("created") or result.get("updated"):
		if result.get("name"):
			actions.append(doc_link(result.get("created") or result.get("updated"), result["name"]))
		lines = [
			_("Created: {0} {1}").format(
				_(result.get("created") or result.get("updated") or ""), result.get("name") or ""
			)
		]
		for row in result.get("lines") or []:
			lines.append(
				f"- {row.get('item')}: {_format_value(row.get('qty'))} × {_format_value(row.get('rate'))}"
			)
		if result.get("grand_total"):
			lines.append(_("Total: {0}").format(_format_value(result["grand_total"])))
		return "\n".join(lines), actions
	if tool == "search_documents":
		rows = result.get("rows") or []
		if not rows:
			return _("Nothing found."), actions
		columns = [c for c in rows[0].keys()][:6]
		labels = {}
		doctype = args.get("doctype")
		if doctype and frappe.db.exists("DocType", doctype):
			meta = frappe.get_meta(doctype)
			labels = {c: _(meta.get_label(c)) if meta.has_field(c) else _(c) for c in columns}
			labels["name"] = _(doctype)

		def cell(row, column):
			if column == "name" and doctype and isinstance(row.get("name"), str):
				from iran_erp.ai.tools import get_url_to_form

				return f"[{row['name']}]({get_url_to_form(doctype, row['name'])})"
			return _format_value(row.get(column))

		body = _table(columns, [[cell(r, c) for c in columns] for r in rows[:15]], labels)
		more = _("Showing {0} of {1}.").format(15, len(rows)) if len(rows) > 15 else ""
		return "\n\n".join(filter(None, [body, more])), actions
	if tool == "run_report":
		columns = (result.get("columns") or [])[:6]
		rows = result.get("rows") or []
		if not rows:
			return _("Nothing found."), actions
		actions.append(link(_("Open the report"), f"/desk/query-report/{args.get('report_name')}"))
		body_rows = []
		for row in rows[:15]:
			if isinstance(row, dict):
				body_rows.append([_format_value(row.get(c["fieldname"])) for c in columns])
			elif isinstance(row, list):
				body_rows.append([_format_value(v) for v in row[: len(columns)]])
		return _table([c["label"] or c["fieldname"] for c in columns], body_rows), actions
	if tool == "get_document":
		lines = [
			f"- {_(k)}: {_format_value(v)}" for k, v in list(result.items())[:12] if v not in (None, "", [])
		]
		if result.get("url"):
			actions.append(link(_("Open"), result["url"]))
		return "\n".join(lines), actions
	return "", actions


def run(name: str, message, values: dict, confirmed: bool = False) -> dict:
	"""Run a recipe for a message; raises NeedSlot / NeedConfirm like a command handler."""
	from iran_erp.ai.tools import execute_tool
	from iran_erp.commands.engine import NeedConfirm, NeedSlot

	recipe = frappe.get_doc("Iran Learned Recipe", name)
	slots = json.loads(recipe.slots or "{}")
	steps = json.loads(recipe.steps or "[]")
	filled, missing = _read_values(slots, message.text, values)
	# Kept in the conversation, so the answer to the next question or a "yes" does not lose them
	values.update({k: v for k, v in filled.items() if k in slots})
	if missing:
		kind = slots[missing]["type"]
		raise NeedSlot(missing, QUESTIONS.get(kind, _("Please give more detail.")))
	amounts = dict(filled)
	for key in _toman_slots(steps):
		if isinstance(amounts.get(key), int | float):
			amounts[key] = amounts[key] * 10
	concrete = [{"tool": s["tool"], "args": _fill(s["args"], amounts)} for s in steps]
	if recipe.writes and not confirmed:
		raise NeedConfirm(
			_("I learned how to do this from the AI model; I will create {0}.").format(_summary(concrete))
			+ _details_text(slots, amounts)
		)

	parts, actions = [], []
	for step in concrete:
		result, _action = execute_tool(step["tool"], step["args"])
		if isinstance(result, dict) and result.get("error"):
			frappe.db.rollback()
			failures = (recipe.failures or 0) + 1
			recipe.db_set({"failures": failures, "enabled": int(failures < MAX_FAILURES)}, commit=True)
			return {
				"answer": _("This could not be done the learned way: {0}").format(result["error"]),
				"delegate_on_error": True,
			}
		text, step_actions = _render(step["tool"], step["args"], result)
		if text:
			parts.append(text)
		actions += step_actions
	recipe.db_set("uses", (recipe.uses or 0) + 1, update_modified=False)
	header = "**" + _("Done the way I learned it from the AI model") + "**"
	return {"answer": "\n\n".join([header, *parts]), "actions": actions}


def disable(name: str):
	if frappe.db.exists("Iran Learned Recipe", name):
		frappe.db.set_value("Iran Learned Recipe", name, "enabled", 0)
		from iran_erp.commands.engine import reset_matcher

		reset_matcher()
