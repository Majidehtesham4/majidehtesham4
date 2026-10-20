"""The dealership's cars, answered the way they are asked for. Three capabilities share one reading
of the request (vehicle_filters and query.shape) and differ in what they return:

- car_stock: the lot, counted and summed, or listed (all of it only when «همه» is said), or ranked
  by price;
- car_search: particular cars by model, year, colour, plate or chassis number, in any state, sold
  and gone included, to say where each one is;
- car_aging: the cars that have stood longest, from their entry date.

Every filter read from the request goes into the query and into the link, and into the request's
details for the trace. A filter that cannot be applied is said, never dropped in silence.
"""

import re

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from iran_erp.commands.engine import NeedSlot, Reroute
from iran_erp.commands.handlers import jdate, link, list_url, money, number, report_url, require, table
from iran_erp.commands.query import shape
from iran_erp.commands.entities import _command_words
from iran_erp.commands.text import normalize, stem, tokens

LOT = ("Awaiting Delivery", "In Preparation", "Ready for Sale", "Reserved")
OWNER_WORDS = (
	("Customer", ("امانی", "امانت")),
	("Investor", ("سرمایه گذار", "سرمایه گذاران", "سرمایهگذار")),
	("Business", ("خود نمایشگاه", "متعلق به نمایشگاه", "دارایی", "ملکی", "خودمون", "خودمان")),
)
STATUS_WORDS = (
	("Ready for Sale", ("اماده فروش", "آماده فروش", "اماده ی فروش")),
	("Reserved", ("رزرو", "رزروی", "رزرو شده")),
	("In Preparation", ("در حال اماده سازی", "اماده سازی", "تعمیر")),
	("Awaiting Delivery", ("در انتظار تحویل", "منتظر تحویل")),
	("Sold", ("فروخته شده", "فروخته", "فروش رفته", "فروختیم", "فروخته شدن")),
	("Exited", ("خارج شده", "تحویل داده شده", "رفته")),
)
COLOR_SYNONYMS = {"سیاه": "مشکی", "سفيد": "سفید", "نقره ای": "نقره‌ای", "طوسی": "خاکستری"}
# A model's own name starts with a word like these only by accident
GENERIC = {"لیتر", "توربو", "اتوماتیک", "دنده", "ای", "پلاس", "پرو", "مکس", "مونتاژ", "سدان"}
# Words that ask where a car is, or whether it was sold
CHECK_WORDS = ("چک کن", "چک", "وضعیت", "فروخته", "فروش رفته", "کجاست", "کجاس", "هنوز")
FIELDS = [
	"name", "title", "car_model", "year", "color", "plate", "status", "branch", "ownership", "asking_price",
	"entry_date", "exit_date", "sold_price", "sale_contract", "creation", "chassis_number",
]  # fmt: skip


def has_cars() -> bool:
	return bool(frappe.db.table_exists("Iran Vehicle") and frappe.db.count("Iran Vehicle"))


def car_spec(text: str) -> str | None:
	"""The words of a request that name a particular car (model, year, colour, chassis number), or
	None: a request about one car has them, one about the lot does not."""
	if not frappe.db.table_exists("Iran Car Model"):
		return None
	words = tokens(text)
	models, label = _models(words)
	years, year_label = _years(text)
	color = _colors(words)
	code = next((w for w in str(text).split() if re.fullmatch(r"[A-Za-z0-9]{8,17}", w)), None)
	parts = [p for p in (label if models else None, year_label, color, code) if p]
	return " ".join(parts) or None


def _can_see_books() -> bool:
	from iran_erp.iran_dealership.dashboard import can_see_books

	return can_see_books()


def _text(context) -> str:
	"""The request; with the car's description when it came separately (a reply, or the AI reader)."""
	text = context.message.text or ""
	car = context.get("car")
	if car and car not in text and not car_spec(text):
		text = f"{text} {car}"
	return text.strip()


def _contains(words, part) -> int | None:
	"""Where the words of `part` appear one after another in `words`."""
	n = len(part)
	for i in range(len(words) - n + 1):
		if words[i : i + n] == part:
			return i
	return None


def _models(words) -> tuple[list[str], str | None]:
	"""The car models a request names: the models named by their own word («K7», «تیگو ۷»), tied
	models included, or every model of a brand («کی‌ام‌سی»), the brand also counting when it is part
	of a model's name («کرمان‌موتور کی‌ام‌سی K7»). Returns (models, how they were named)."""
	rows = frappe.get_all("Iran Car Model", fields=["name", "brand", "model", "title"])
	said = set(words)
	# Words people ask with («خودرو», «ماشین») are not part of a name, though «ایران‌خودرو» has one
	asking = _command_words()
	named = {r.brand: tokens(r.brand) for r in rows if r.brand and _contains(words, tokens(r.brand)) is not None}
	brands = list(named.values())
	brand_words = {w for brand in brands for w in brand}
	specific, best = [], 0
	for row in rows:
		title = tokens(row.title or f"{row.brand or ''} {row.model or ''}")
		# Words of its name the request has, beyond the brand: a model is named only by those
		own = [w for w in title if w in said and w not in brand_words and w not in GENERIC and stem(w) not in asking]
		if not own or all(w.replace(".", "").isdigit() for w in own):
			continue
		score = len([w for w in title if w in said])
		if score > best:
			specific, best = [row], score
		elif score == best:
			specific.append(row)
	if specific:
		label = specific[0].title if len(specific) == 1 else "، ".join(r.title for r in specific[:4])
		return [r.name for r in specific], label
	if brands:
		chosen = [r for r in rows if any(_contains(tokens(r.title or r.brand or ""), b) is not None for b in brands)]
		return [r.name for r in chosen], "، ".join(sorted(named))
	return [], None


def _years(text) -> tuple[list[str], str | None]:
	"""Model years said: a Solar Hijri year also matches its Gregorian one (۱۴۰۳ ↔ ۲۰۲۴)."""
	for found in re.findall(r"(?<!\d)(1[34]\d\d|19\d\d|20\d\d)(?!\d)", normalize(text)):
		year = int(found)
		other = year + 621 if year < 1500 else year - 621
		return [str(year), str(other)], f"{year} ({other})"
	return [], None


def _colors(words) -> str | None:
	text = " ".join(words)
	for wrong, right in COLOR_SYNONYMS.items():
		text = text.replace(wrong, right)
	words = text.split()
	colors = sorted(frappe.get_all("Iran Car Color", pluck="name"), key=lambda c: -len(tokens(c)))
	return next((c for c in colors if _contains(words, tokens(c)) is not None), None)


def _phrase(text, table_):
	hay = f" {normalize(text)} "
	return next((key for key, phrases in table_ if any(f" {normalize(p)} " in hay for p in phrases)), None)


def vehicle_filters(context, statuses=LOT, read_status=True) -> tuple[dict, list[str], dict]:
	"""(filters for Iran Vehicle, the filters in words, the details for the trace) from a request:
	model or brand, model year, colour, owner, state, branch, plate or chassis number."""
	text = _text(context)
	words = tokens(text)
	filters, said, spec = {}, [], {}
	models, label = _models(words)
	if models:
		filters["car_model"] = ["in", models]
		said.append(label)
		spec["model"] = label
	years, year_label = _years(text)
	if years:
		filters["year"] = ["in", years]
		said.append(_("model year {0}").format(year_label))
		spec["year"] = years[0]
	color = _colors(words)
	if color:
		filters["color"] = color
		said.append(color)
		spec["color"] = color
	code = next((w for w in str(text).split() if re.fullmatch(r"[A-Za-z0-9]{8,17}", w)), None)
	if code:
		filters["chassis_number"] = ["like", f"%{code}%"]
		said.append(code)
		spec["chassis"] = code
	ownership = _phrase(text, OWNER_WORDS)
	if ownership:
		filters["ownership"] = ownership
		said.append(_(ownership))
		spec["ownership"] = ownership
	status = _phrase(text, STATUS_WORDS) if read_status else None
	if status:
		filters["status"] = status
		said.append(_(status))
		spec["status"] = status
	elif statuses:
		filters["status"] = ["in", list(statuses)]
	if context.get("branch"):
		filters["branch"] = context.get("branch")
		said.append(context.get("branch"))
		spec["branch"] = context.get("branch")
	# The trace shows what was read; the handler runs on the same filters
	context.values.update(spec)
	return filters, said, spec


def _shape(context) -> dict:
	result = shape(_text(context))
	context.values.update({k: v for k, v in result.items()})
	return result


def _car(c) -> str:
	return f"[{c.title or c.car_model or c.name}](/desk/iran-vehicle/{c.name})"


def _report_filters(filters) -> dict:
	"""The Vehicles in Stock report's filters for the same cars."""
	out = {}
	for key in ("branch", "ownership"):
		if isinstance(filters.get(key), str):
			out[key] = filters[key]
	if isinstance(filters.get("status"), str):
		out["status"] = filters["status"]
	if filters.get("car_model"):
		out["car_models"] = ",".join(filters["car_model"][1])
	if filters.get("year"):
		out["year"] = ",".join(filters["year"][1])
	if filters.get("color"):
		out["color"] = filters["color"]
	return out


# ---------------------------------------------------------------- the lot


def car_stock(context):
	"""The cars in the lot: counted, summed, listed or ranked by price, with the filters said."""
	require("Iran Vehicle")
	text = _text(context)
	result = _shape(context)
	# How long cars have stood is its own report
	if result.get("order") == "longest":
		raise Reroute("car_aging")
	filters, said, spec = vehicle_filters(context)
	# A particular car, asked about: where it is, sold or not
	if {"model", "year", "color", "chassis"} & set(spec) and any(
		f" {normalize(w)} " in f" {normalize(text)} " for w in CHECK_WORDS
	):
		raise Reroute("car_search")
	order_by = {
		"price_high": "asking_price desc",
		"price_low": "asking_price asc",
		"newest": "entry_date desc, creation desc",
	}.get(result.get("order"), "entry_date desc, creation desc")
	cars = frappe.get_list("Iran Vehicle", filters=filters, fields=FIELDS, order_by=order_by, limit_page_length=0)
	scope = "، ".join(said) if said else _("every branch, every owner")
	actions = [link(_("These cars"), list_url("Iran Vehicle", filters)), link(_("Dealership dashboard"), "/desk/iran-dealership")]
	if not cars:
		return {"answer": _("No cars in the lot ({0}).").format(scope), "actions": actions, "records": 0, "matched": 0}

	output = result.get("output")
	if output == "count":
		return {"answer": _("Cars in the lot ({0}): {1}").format(scope, number(len(cars))) + "\n\n" + _breakdown(cars), "actions": actions, "records": 0, "matched": len(cars)}
	if result.get("order") in ("price_high", "price_low"):
		top = cars[: 1 if output == "one" else result.get("limit") or 10]
		title = _("Most expensive") if result["order"] == "price_high" else _("Cheapest")
		return {"answer": f"**{title}** ({scope})\n\n" + _car_table(top), "actions": actions, "records": len(top), "matched": len(cars)}
	if output == "all":
		return {
			"answer": _("All cars in the lot ({0}): {1}").format(scope, number(len(cars))) + "\n\n" + _car_table(cars),
			"actions": actions,
			"records": len(cars),
			"matched": len(cars),
		}
	shown = cars[:15]
	lines = [_("Cars in the lot ({0}): {1}").format(scope, number(len(cars))), "", _breakdown(cars), "", _car_table(shown)]
	if len(cars) > len(shown):
		lines.append(_("The newest {0} of {1}; the list has them all.").format(number(len(shown)), number(len(cars))))
	return {"answer": "\n".join(lines), "actions": actions, "records": len(shown), "matched": len(cars)}


def _breakdown(cars) -> str:
	def by(key):
		counts = {}
		for c in cars:
			counts[c[key]] = counts.get(c[key], 0) + 1
		return counts

	lines = ["- " + "، ".join(f"{_(s)}: {number(n)}" for s, n in by("status").items())]
	lines.append("- " + "، ".join(f"{_(o)}: {number(n)}" for o, n in by("ownership").items()))
	branches = by("branch")
	if len(branches) > 1:
		lines.append("- " + "، ".join(f"{b or _('No branch set')}: {number(n)}" for b, n in branches.items()))
	if _can_see_books():
		lines.append("- " + _("Asking prices in total: {0}").format(money(sum(flt(c.asking_price) for c in cars))))
	return "\n".join(lines)


def _car_table(cars) -> str:
	return table(
		[_("Car"), _("Year"), _("Color"), _("Status"), _("Asking Price")],
		[[_car(c), c.year or "", c.color or "", _(c.status), money(c.asking_price)] for c in cars],
	)


# ---------------------------------------------------------------- one car


def car_search(context):
	"""Particular cars, in any state: in the lot, reserved, sold or gone; whether each was sold."""
	require("Iran Vehicle")
	if context.get("vehicle"):
		return _one_car(frappe.get_doc("Iran Vehicle", context.get("vehicle")))
	filters, said, spec = vehicle_filters(context, statuses=None, read_status=False)
	if not ({"model", "year", "color", "chassis"} & set(spec)):
		raise NeedSlot("car", _("Which car? Write its model, year, colour or plate."))
	cars = frappe.get_list("Iran Vehicle", filters=filters, fields=FIELDS, order_by="entry_date desc", limit_page_length=0)
	scope = "، ".join(said)
	actions = [link(_("These cars"), list_url("Iran Vehicle", filters))]
	if not cars:
		answer = _("No car with {0} was found, among the cars in the lot, sold or gone.").format(scope)
		near = _near(filters)
		if near:
			# Said as what they are: other cars, not the one asked about
			answer += "\n\n" + _("Not the same, but close (one detail differs):") + "\n\n" + table(
				[_("Car"), _("Year"), _("Color"), _("Status")], [[_car(c), c.year or "", c.color or "", _(c.status)] for c in near]
			)
		return {"answer": answer, "actions": [link(_("Cars"), list_url("Iran Vehicle"))], "records": 0, "matched": 0}
	if len(cars) == 1:
		return {**_one_car(frappe.get_doc("Iran Vehicle", cars[0].name)), "matched": 1}
	sold = [c for c in cars if c.status in ("Sold", "Exited")]
	summary = _("{0} cars with {1}: {2} sold, {3} still here.").format(
		number(len(cars)), scope, number(len(sold)), number(len(cars) - len(sold))
	)
	rows = [[_car(c), c.year or "", c.color or "", _(c.status), jdate(c.entry_date) if c.entry_date else ""] for c in cars]
	answer = summary + "\n\n" + table([_("Car"), _("Year"), _("Color"), _("Status"), _("Entry Date")], rows)
	if len(cars) <= 6:
		# Only the matching cars to choose from, to see one in full
		raise NeedSlot(
			"vehicle",
			answer + "\n\n" + _("Which one shall I show in full?"),
			[(c.name, f"{c.title or c.car_model} — {_(c.status)}") for c in cars],
		)
	return {"answer": answer, "actions": actions, "records": len(cars), "matched": len(cars)}


def _near(filters, limit=5) -> list:
	"""Cars that match every detail but one (the year or the colour), to show next to «not found»."""
	near = []
	for loose in ("year", "color"):
		if loose not in filters or len(filters) < 2:
			continue
		rest = {k: v for k, v in filters.items() if k != loose}
		near += frappe.get_list("Iran Vehicle", filters=rest, fields=FIELDS, order_by="entry_date desc", limit_page_length=limit)
	seen = set()
	return [c for c in near if not (c.name in seen or seen.add(c.name))][:limit]


def _one_car(doc) -> dict:
	lines = [f"**{doc.title or doc.car_model}** ({doc.name})", ""]
	if doc.status in ("Sold", "Exited"):
		when = doc.exit_date
		contract = None
		if doc.sale_contract and frappe.has_permission("Iran Instalment Sale", "read", doc.sale_contract):
			contract = frappe.db.get_value("Iran Instalment Sale", doc.sale_contract, ["posting_date", "customer_name"], as_dict=True)
			when = when or (contract and contract.posting_date)
		lines.append("- " + _("Sold: yes") + (f" ({jdate(when)})" if when else ""))
		if contract and contract.customer_name:
			lines.append("- " + _("Buyer: {0}").format(contract.customer_name))
		if doc.sold_price and _can_see_books():
			lines.append("- " + _("Sale price: {0}").format(money(doc.sold_price)))
	else:
		lines.append("- " + _("Sold: no; status in the lot: {0}").format(_(doc.status)))
		if doc.entry_date:
			lines.append("- " + _("In the lot since {0} ({1} days)").format(jdate(doc.entry_date), number(date_diff(nowdate(), doc.entry_date))))
	for label, value in ((_("Year"), doc.year), (_("Color"), doc.color), (_("Plate"), doc.plate), (_("Branch"), doc.branch)):
		if value:
			lines.append(f"- {label}: {value}")
	actions = [link(doc.title or doc.name, f"/desk/iran-vehicle/{doc.name}")]
	if doc.sale_contract:
		actions.append(link(_("Sale Contract"), f"/desk/iran-instalment-sale/{doc.sale_contract}"))
	return {"answer": "\n".join(lines), "actions": actions, "records": 1}


# ---------------------------------------------------------------- time in the lot


def car_aging(context):
	"""The cars that have stood longest, counted from their entry date: the first one (and any tied
	with it), the first few, or all of them, longest first."""
	require("Iran Vehicle")
	result = _shape(context)
	filters, said, _spec = vehicle_filters(context)
	cars = frappe.get_list("Iran Vehicle", filters=filters, fields=FIELDS, order_by="entry_date asc, creation asc", limit_page_length=0)
	scope = "، ".join(said) if said else _("every branch, every owner")
	actions = [link(_("Vehicles in Stock, longest first"), report_url("Vehicles in Stock", _report_filters(filters)))]
	if not cars:
		return {"answer": _("No cars in the lot ({0}).").format(scope), "actions": actions, "records": 0, "matched": 0}
	dated = [c for c in cars if c.entry_date]
	undated = len(cars) - len(dated)
	if not dated:
		return {
			"answer": _("The entry date is not recorded for any of these {0} cars, so how long they have stood cannot be told. Fill in «Entry Date» on each car's file.").format(number(len(cars))),
			"actions": actions,
			"records": 0,
			"matched": len(cars),
		}
	today = getdate(nowdate())
	for c in dated:
		c.days = (today - getdate(c.entry_date)).days
	dated.sort(key=lambda c: -c.days)
	output = result.get("output") or "top"
	if output == "one":
		shown = [c for c in dated if c.days == dated[0].days]
		title = _("Longest in the lot") if len(shown) == 1 else _("Longest in the lot: {0} cars entered the same day").format(number(len(shown)))
		shown = shown[:10]
	elif output == "all":
		shown, title = dated, _("All cars in the lot, longest first")
	else:
		shown = dated[: result.get("limit") or 10]
		title = _("The {0} cars longest in the lot").format(number(len(shown)))
	lines = [f"**{title}** ({scope})", ""]
	lines.append(
		table(
			[_("Car"), _("Entry Date"), _("Days in the Lot"), _("Status"), _("Branch")],
			[[_car(c), jdate(c.entry_date), number(c.days), _(c.status), c.branch or ""] for c in shown],
		)
	)
	notes = []
	if undated:
		notes.append(_("{0} cars have no entry date and are not in this list.").format(number(undated)))
	# Cars entered all at once, on the day their files were made: the dates may be the import's, not the arrival's
	same_day = [c for c in dated if getdate(c.entry_date) == getdate(c.creation)]
	common = max((sum(1 for c in dated if c.entry_date == d.entry_date) for d in dated), default=0)
	if common >= max(5, len(dated) // 2) and len(same_day) >= common:
		notes.append(
			_("{0} cars have the same entry date, the day their files were made; if they arrived earlier, correct «Entry Date» on their files for this report to be right.").format(number(common))
		)
	if notes:
		lines += [""] + [f"- {n}" for n in notes]
	return {"answer": "\n".join(lines), "actions": actions, "records": len(shown), "matched": len(dated)}
