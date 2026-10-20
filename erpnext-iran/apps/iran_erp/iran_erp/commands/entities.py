"""Find the customers, items and other records a message names, by matching their names."""

import frappe

from iran_erp.commands.text import STOPWORDS, stem, tokens

# kind: doctype, name fields to match, filters, the field shown to the user
SOURCES = {
	"customer": ("Customer", ("customer_name", "name"), {"disabled": 0}, "customer_name"),
	"supplier": ("Supplier", ("supplier_name", "name"), {"disabled": 0}, "supplier_name"),
	"item": ("Item", ("item_name", "name"), {"disabled": 0}, "item_name"),
	"warehouse": ("Warehouse", ("warehouse_name", "name"), {"is_group": 0}, "warehouse_name"),
	"account": ("Account", ("account_name", "name"), {"is_group": 0, "disabled": 0}, "name"),
	"cash_account": (
		"Account",
		("account_name", "name"),
		{"is_group": 0, "disabled": 0, "account_type": ["in", ["Cash", "Bank"]]},
		"name",
	),
	# The company's bank accounts by the names people use: "حساب ملت", "بانک ملت شرکا"
	"bank_account": (
		"Bank Account",
		("account_name", "bank", "name"),
		{"disabled": 0, "is_company_account": 1},
		"name",
	),
	"project": ("Project", ("project_name", "name"), {}, "project_name"),
	"employee": ("Employee", ("employee_name", "name"), {"status": "Active"}, "employee_name"),
	"lead": ("Lead", ("lead_name", "company_name", "name"), {}, "lead_name"),
	"item_group": ("Item Group", ("name",), {"is_group": 0}, "name"),
	"bom": ("BOM", ("name", "item_name"), {"is_active": 1, "docstatus": 1}, "name"),
	"investor": ("Iran Investor", ("full_name", "name"), {}, "full_name"),
	"user": ("User", ("full_name", "username", "name"), {"enabled": 1, "name": ["not in", ["Guest"]]}, "full_name"),
	"branch": ("Branch", ("name",), {}, "name"),
}
# Titles say nothing about who is meant: «خانم کریمی» is not «خانم احمدی»
HONORIFICS = {"اقای", "اقا", "خانم", "جناب", "سرکار", "دکتر", "مهندس", "حاج", "حاجی", "اقایان"}
MAX_RECORDS = 20000
MAX_WINDOW = 6
CACHE_SECONDS = 120


class Found:
	def __init__(self, name=None, label=None, used=(), options=(), score=0, asked=None):
		self.name = name
		self.score = score
		self.label = label
		self.used = set(used)
		# Several records fit equally well: the user has to choose
		self.options = list(options)
		# The name as asked, when no record has it exactly and the options are only the closest
		self.asked = asked

	def __bool__(self):
		return bool(self.name)


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _cache_key(kind):
	return f"iran_cmd_entities:v2:{kind}:{frappe.session.user}:{_company()}"


def forget(kind: str):
	"""Drop the cached names after creating a record, so the next message finds it."""
	frappe.cache.delete_value(_cache_key(kind))
	(getattr(frappe.local, "iran_cmd_index", None) or {}).pop(kind, None)


def _records(kind) -> list[tuple[str, str, list[list[str]]]]:
	"""(name, label, [name variants as token lists]) for every record of a kind the user can read."""
	key = _cache_key(kind)
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached
	doctype, fields, filters, label_field = SOURCES[kind]
	if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
		return []
	meta = frappe.get_meta(doctype)
	filters = {k: v for k, v in filters.items() if meta.has_field(k)}
	# Warehouses, accounts and projects of the company being worked in
	if meta.has_field("company") and _company():
		filters["company"] = _company()
	fields = [f for f in fields if f == "name" or meta.has_field(f)]
	label_field = label_field if label_field == "name" or meta.has_field(label_field) else "name"
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=list(dict.fromkeys(["name", label_field, *fields])),
		limit=MAX_RECORDS,
		order_by="modified desc",
	)
	records = []
	for row in rows:
		variants = []
		for field in fields:
			value = row.get(field) or ""
			if field == "name" and kind in ("account", "cash_account"):
				# "1101 - صندوق - KB": the number and the name, without the company suffix
				value = value.rsplit(" - ", 1)[0]
			# The same reading as messages get, so names and messages compare word for word
			words = [w for w in tokens(value) if w != ","]
			if words and words not in variants:
				variants.append(words)
		records.append((row.name, row.get(label_field) or row.name, variants))
	frappe.cache.set_value(key, records, expires_in_sec=CACHE_SECONDS)
	return records


def _same(a: str, b: str) -> bool:
	return a == b or (len(a) > 3 and stem(a) == stem(b))


def _window_matches(window, variant) -> bool:
	n = len(window)
	return any(
		all(_same(window[k], variant[start + k]) for k in range(n)) for start in range(len(variant) - n + 1)
	)


def _index(kind, records) -> dict[str, set[int]]:
	"""Stemmed word -> positions of the records whose name has it, built once per request."""
	cache = getattr(frappe.local, "iran_cmd_index", None)
	if cache is None:
		cache = frappe.local.iran_cmd_index = {}
	if kind not in cache:
		index = {}
		for position, (_name, _label, variants) in enumerate(records):
			for variant in variants:
				for word in variant:
					index.setdefault(stem(word), set()).add(position)
		cache[kind] = index
	return cache[kind]


def _command_words() -> set[str]:
	"""Stems of every word the command samples use: "تامین کننده" is how users ask, not a name."""
	cache = getattr(frappe.local, "iran_cmd_words", None)
	if cache is None:
		from iran_erp.commands.catalog import DOCTYPES, INTENTS, REPORTS
		from iran_erp.commands.text import tokens

		texts = [e for intent in INTENTS for e in intent["examples"]]
		texts += [n for names in (*DOCTYPES.values(), *REPORTS.values()) for n in names]
		cache = {
			stem(w)
			for text in texts
			for w in tokens(text.replace("{", " ").replace("}", " "))
			if not w.isdigit()
		}
		frappe.local.iran_cmd_words = cache
	return cache


def find(kind: str, words: list[str], skip: set[int] = frozenset()) -> Found:
	"""The record of `kind` named by the longest run of words; `skip` are positions used for other things."""
	records = _records(kind)
	if not records:
		return Found()
	index = _index(kind, records)
	best_score, best = 0, {}
	for i in range(len(words)):
		candidates = None
		for j in range(i + 1, min(len(words), i + MAX_WINDOW) + 1):
			if j - 1 in skip:
				break
			found_here = index.get(stem(words[j - 1]), set())
			candidates = found_here if candidates is None else candidates & found_here
			if not candidates:
				break
			window = words[i:j]
			if all(w in STOPWORDS or w in HONORIFICS or len(w) < 2 for w in window):
				continue
			if j - i == 1 and window[0].isdigit() and len(window[0]) < 3:
				continue
			generic = all(stem(w) in _command_words() or w in STOPWORDS for w in window)
			for position in candidates:
				name, label, variants = records[position]
				for variant in variants:
					if not _window_matches(window, variant):
						continue
					if generic and len(variant) != j - i:
						continue
					# Longer matches win; a whole name beats a part of one
					score = (j - i) * 10 + (5 if len(variant) == j - i else 0) - (len(variant) - (j - i))
					if score > best_score:
						best_score, best = score, {name: (label, set(range(i, j)))}
					elif score == best_score:
						best.setdefault(name, (label, set(range(i, j))))
	if not best:
		return Found()
	# «خانم کریمی» when only «آقای کریمی» is on record: the closest, to confirm, not taken as said
	title = _title_before(words, min(min(u) for _l, u in best.values()))
	if title:
		same = {n: v for n, v in best.items() if not _other_title(records, n, title)}
		if not same:
			used = set().union(*(u for _, u in best.values())) | {min(min(u) for _l, u in best.values()) - 1}
			asked = " ".join(words[min(used) : max(used) + 1])
			options = [(name, label) for name, (label, _) in list(best.items())[:6]]
			return Found(used=used, options=options, score=best_score, asked=asked)
		best = same
	if len(best) == 1:
		name, (label, used) = next(iter(best.items()))
		return Found(name, label, used, score=best_score)
	used = set().union(*(u for _, u in best.values()))
	return Found(
		used=used, options=[(name, label) for name, (label, _) in list(best.items())[:6]], score=best_score
	)


def _title_before(words, start) -> str | None:
	return words[start - 1] if start > 0 and words[start - 1] in HONORIFICS else None


def _other_title(records, name, title) -> bool:
	"""Whether the record's name carries a title other than the one asked («آقای» for «خانم»)."""
	for record_name, _label, variants in records:
		if record_name == name:
			titles = {w for variant in variants for w in variant if w in HONORIFICS}
			return bool(titles) and title not in titles
	return False
