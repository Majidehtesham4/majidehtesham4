"""Read a command's details (slots) out of a message: who, what, how many, how much, when."""

import re

import frappe

from iran_erp.commands import entities
from iran_erp.commands.catalog import DOCTYPES, PAYMENT_MODES, REPORTS
from iran_erp.commands.text import (
	PRICE_WORDS,
	QTY_WORDS,
	RIAL,
	SEPARATOR,
	STOPWORDS,
	TOMAN,
	find_date,
	find_mobile,
	find_numbers,
	find_period,
	normalize,
	pieces,
	stem,
	to_rial,
	tokens,
	yes_no,
)

ENTITY_KINDS = {
	"customer",
	"supplier",
	"item",
	"warehouse",
	"account",
	"cash_account",
	"bank_account",
	"project",
	"employee",
	"lead",
	"investor",
	"user",
	"branch",
}
# Document names look like ACC-SINV-2026-00006 or CHQ-2026-00012
DOCUMENT_NAME = re.compile(r"^[a-z]{2,}(-[a-z0-9]+)*-\d+$")
DOCUMENT_DOCTYPES = (
	"Sales Invoice",
	"Purchase Invoice",
	"Quotation",
	"Sales Order",
	"Purchase Order",
	"Payment Entry",
	"Journal Entry",
	"Delivery Note",
	"Purchase Receipt",
	"Stock Entry",
	"Material Request",
	"Work Order",
	"Iran Cheque",
)
CITY_MARKERS = {"از", "شهر", "ساکن", "در"}
NAME_MARKERS = {"اسم", "نام", "بهاسم", "بنام"}


class Ambiguous(Exception):
	"""Several records fit: the user has to pick one. note: what to say first («خانم کریمی» was
	not found; these are the closest)."""

	def __init__(self, slot, options, note=None):
		super().__init__(slot)
		self.slot = slot
		self.options = options
		self.note = note


def _not_exact(found) -> str | None:
	from frappe import _

	return _("No one named «{0}» is on record. Did you mean:").format(found.asked) if found.asked else None


class Message:
	def __init__(self, text: str, keywords: set[str] = frozenset()):
		self.text = text
		self.pieces = pieces(text)
		self.words = [w for w, _ in self.pieces]
		self.originals = [o for _, o in self.pieces]
		# Positions already read as something, or that are the command's own wording
		self.used = set()
		self.keywords = {i for i, w in enumerate(self.words) if stem(w) in keywords}
		self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		self.currency = (
			frappe.db.get_value("Company", self.company, "default_currency") if self.company else "IRR"
		)

	def free(self) -> set[int]:
		return set(range(len(self.words))) - self.used

	def blocked(self) -> set[int]:
		return self.used | self.keywords

	def leftover(self, skip_stopwords=True) -> list[int]:
		return [
			i
			for i in range(len(self.words))
			if i not in self.used
			and i not in self.keywords
			and self.words[i] != SEPARATOR
			and not (skip_stopwords and self.words[i] in STOPWORDS)
		]

	def text_of(self, positions) -> str:
		return " ".join(self.originals[i] for i in sorted(positions)).strip()


def extract(slot_type: str, message: Message, slot_name: str = ""):
	"""The value of one slot, or None. Raises Ambiguous when several records fit equally well."""
	reader = READERS.get(slot_type)
	return reader(message, slot_name) if reader else None


def _entity(kind):
	def read(message, slot_name):
		found = entities.find(kind, message.words, message.blocked())
		if found.options:
			message.used |= found.used
			raise Ambiguous(slot_name or kind, found.options, _not_exact(found))
		if found:
			message.used |= found.used
			return found.name
		return None

	return read


def _party(message, slot_name, kinds=("customer", "supplier")):
	results = []
	for kind in kinds:
		found = entities.find(kind, message.words, message.blocked())
		if found or found.options:
			results.append((found.score, kind, found))
	if not results:
		return None
	results.sort(key=lambda r: r[0], reverse=True)
	score, kind, found = results[0]
	tied = [r for r in results if r[0] == score]
	if len(tied) > 1 or found.options:
		options = []
		for _score, tied_kind, tied_found in tied:
			if tied_found:
				options.append((f"{tied_kind}:{tied_found.name}", tied_found.label))
			options += [(f"{tied_kind}:{name}", label) for name, label in tied_found.options]
		message.used |= found.used
		raise Ambiguous(slot_name, options[:6], _not_exact(found))
	message.used |= found.used
	return f"{kind}:{found.name}"


def _party_or_account(message, slot_name):
	return _party(message, slot_name, ("customer", "supplier", "cash_account", "account"))


def _dictionary(table):
	"""The key whose Persian name appears in the message, the longest name winning."""
	variants = sorted(
		((key, tokens(name)) for key, names in table.items() for name in names),
		key=lambda v: len(v[1]),
		reverse=True,
	)

	def read(message, slot_name):
		words = [stem(w) for w in message.words]
		for key, variant in variants:
			n = len(variant)
			target = [stem(w) for w in variant]
			for i in range(len(words) - n + 1):
				if words[i : i + n] == target and not (set(range(i, i + n)) & message.used):
					message.used |= set(range(i, i + n))
					return key
		return None

	return read


def _document(message, slot_name):
	"""A document named by its full name, or by its number together with its kind."""
	kind = _dictionary(DOCTYPES)(message, "")
	doctypes = [kind] if kind in DOCUMENT_DOCTYPES else list(DOCUMENT_DOCTYPES)
	for i, word in enumerate(message.words):
		if i in message.used:
			continue
		if DOCUMENT_NAME.match(word):
			for doctype in doctypes:
				name = frappe.db.get_value(doctype, {"name": word.upper()}) or frappe.db.get_value(
					doctype, {"name": word}
				)
				if name and frappe.has_permission(doctype, "read", name):
					message.used.add(i)
					return f"{doctype}:{name}"
	for i, word in enumerate(message.words):
		if i in message.used or not word.isdigit():
			continue
		for doctype in doctypes[:1] if kind else ("Sales Invoice", "Purchase Invoice"):
			found = frappe.get_list(
				doctype,
				filters={"name": ["like", f"%-{int(word):05d}"]},
				pluck="name",
				limit=2,
				order_by="creation desc",
			) or frappe.get_list(
				doctype,
				filters={"name": ["like", f"%{word}"]},
				pluck="name",
				limit=2,
				order_by="creation desc",
			)
			if len(found) == 1:
				message.used.add(i)
				return f"{doctype}:{found[0]}"
	return None


def _numbers(message):
	return [n for n in find_numbers(message.words) if not (set(range(n.start, n.end)) & message.used)]


def _amount(message, slot_name):
	numbers = _numbers(message)
	if not numbers:
		return None

	# A number with a currency, or after "قیمت/مبلغ", is the amount; otherwise the largest one
	def after_price_word(n):
		return n.start > 0 and message.words[n.start - 1] in PRICE_WORDS

	chosen = (
		next((n for n in numbers if n.next_word in TOMAN | RIAL), None)
		or next((n for n in numbers if after_price_word(n)), None)
		or max(numbers, key=lambda n: n.value)
	)
	message.used |= set(range(chosen.start, chosen.end))
	if chosen.next_word in TOMAN | RIAL:
		message.used.add(chosen.end)
	return to_rial(chosen, message.currency)


def _qty(message, slot_name):
	numbers = _numbers(message)
	if not numbers:
		return None
	chosen = next((n for n in numbers if n.next_word in QTY_WORDS), None) or min(
		numbers, key=lambda n: n.value
	)
	message.used |= set(range(chosen.start, chosen.end))
	if chosen.next_word in QTY_WORDS:
		message.used.add(chosen.end)
	return chosen.value


def _number(message, slot_name):
	# Long digit strings first: cheque numbers, Sayad IDs, years
	for i, word in enumerate(message.words):
		if i not in message.used and word.isdigit():
			message.used.add(i)
			return word
	numbers = _numbers(message)
	if numbers:
		message.used |= set(range(numbers[0].start, numbers[0].end))
		value = numbers[0].value
		return str(int(value)) if value == int(value) else str(value)
	return None


def _percent(message, slot_name):
	for n in _numbers(message):
		if n.next_word == "درصد":
			message.used |= set(range(n.start, n.end + 1))
			return n.value
	return None


def _limit(message, slot_name):
	for n in _numbers(message):
		if n.value <= 100 and n.value == int(n.value):
			message.used |= set(range(n.start, n.end))
			return int(n.value)
	return None


def _date(message, slot_name):
	words = [w if i not in message.used else "" for i, w in enumerate(message.words)]
	date, used = find_date(words)
	message.used |= used
	return str(date) if date else None


def _period(message, slot_name):
	period, label = find_period([w if i not in message.used else "" for i, w in enumerate(message.words)])
	return {"from": str(period[0]), "to": str(period[1]), "label": label} if period else None


def _mobile(message, slot_name):
	mobile = find_mobile(message.text)
	if mobile:
		for i, word in enumerate(message.words):
			if word.lstrip("+").endswith(mobile[1:]) or mobile[1:] in word:
				message.used.add(i)
	return mobile


def _city(message, slot_name):
	for i, word in enumerate(message.words[:-1]):
		if word in CITY_MARKERS and i + 1 not in message.used and not message.words[i + 1].isdigit():
			following = message.words[i + 1]
			if following in STOPWORDS or following == SEPARATOR:
				continue
			message.used |= {i, i + 1}
			return message.originals[i + 1]
	return None


def _name(message, slot_name):
	"""The name of something new: the words left after the command's own wording."""
	positions = message.leftover(skip_stopwords=False)
	# Cut connecting words off both ends: "مشتری جدید به اسم علی رضایی با ..." -> "علی رضایی"
	while positions and (
		message.words[positions[0]] in STOPWORDS or message.words[positions[0]] in NAME_MARKERS
	):
		positions.pop(0)
	while positions and message.words[positions[-1]] in STOPWORDS:
		positions.pop()
	# Only one run of words: stop at the first gap
	run = []
	for position in positions:
		if run and position != run[-1] + 1:
			break
		run.append(position)
	if not run:
		return None
	message.used |= set(run)
	return message.text_of(run)


def _text(message, slot_name):
	positions = message.leftover(skip_stopwords=False)
	while positions and message.words[positions[0]] in STOPWORDS:
		positions.pop(0)
	if not positions:
		return None
	message.used |= set(positions)
	return message.text_of(positions)


def _vat(message, slot_name):
	text = " " + " ".join(message.words) + " "
	if re.search(r" (بدون|بی) (مالیات|ارزش|ارزشافزوده|vat) ", text) or re.search(
		r" (مالیات|ارزش افزوده) (نداره|نمیخواد|نزن|نذار) ", text
	):
		return "no"
	if re.search(r" با (مالیات|ارزش|ارزشافزوده|vat) ", text) or re.search(
		r" (مالیات|ارزش افزوده) (داره|بزن|بذار|اضافه) ", text
	):
		return "yes"
	answer = yes_no(message.text)
	return None if answer is None else ("yes" if answer else "no")


def _payment_mode(message, slot_name):
	text = " " + " ".join(message.words) + " "
	for mode, words in PAYMENT_MODES.items():
		for word in sorted(words, key=len, reverse=True):
			if f" {normalize(word)} " in text:
				return mode
	return None


def _items(message, slot_name):
	"""Item lines: "۳ تا مانیتور ۲۴ اینچ به قیمت ۱۲ میلیون و ۲ تا پرینتر"."""
	free = [i for i in range(len(message.words)) if i not in message.blocked()]
	if not free:
		return None
	# Split into lines at commas, and at "و" when a number follows
	segments, current = [], []
	for i in free:
		word = message.words[i]
		nxt = message.words[i + 1] if i + 1 < len(message.words) else ""
		if word == SEPARATOR or (
			word == "و"
			and current
			and (nxt.isdigit() or nxt in {"یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "ده", "یه"})
		):
			if current:
				segments.append(current)
			current = []
			continue
		current.append(i)
	if current:
		segments.append(current)

	lines, unknown = [], []
	for segment in segments:
		words = [message.words[i] if i in segment else "" for i in range(len(message.words))]
		blocked = set(range(len(message.words))) - set(segment)
		found = entities.find("item", words, blocked)
		numbers = [
			n for n in find_numbers(words) if not (set(range(n.start, n.end)) & (found.used | blocked))
		]
		if (
			(found or found.options)
			and found.score < 15
			and _extra_words(message, segment, found.used, numbers)
		):
			# Words left over next to a partial name mean a different item: "فر برقی ساده" is not "فر پیتزا"
			unknown.append(message.text_of(segment))
			continue
		if found.options:
			message.used |= found.used
			raise Ambiguous(slot_name, found.options)
		if not found:
			leftover = [
				i for i in segment if message.words[i] not in STOPWORDS and not message.words[i].isdigit()
			]
			if numbers or leftover:
				unknown.append(message.text_of(segment))
			continue
		qty, rate = None, None
		used = set(found.used)
		for n in numbers:
			before = message.words[n.start - 1] if n.start > 0 else ""
			span = set(range(n.start, n.end))
			if (
				n.next_word in TOMAN | RIAL
				or before in PRICE_WORDS
				or (before == "به" and n.start > 1 and message.words[n.start - 2] in PRICE_WORDS)
			):
				rate = to_rial(n, message.currency)
				used |= span | ({n.end} if n.next_word in TOMAN | RIAL else set())
			elif qty is None and (n.next_word in QTY_WORDS or n.value < 10000):
				qty = n.value
				used |= span | ({n.end} if n.next_word in QTY_WORDS else set())
			elif rate is None:
				rate = to_rial(n, message.currency)
				used |= span
		lines.append({"item": found.name, "label": found.label, "qty": qty or 1, "rate": rate})
		# Only what was read; warehouses and other details in the line stay for the other slots
		message.used |= used
	if unknown:
		return {"lines": lines, "unknown": unknown}
	return {"lines": lines, "unknown": []} if lines else None


def _extra_words(message, segment, name_positions, numbers) -> bool:
	"""Whether words around a partly matched item name are left unexplained."""
	number_positions = {i for n in numbers for i in range(n.start, n.end + 1)}
	low, high = min(name_positions) - 3, max(name_positions) + 3
	for i in segment:
		word = message.words[i]
		if i in name_positions or i in number_positions or not low <= i <= high:
			continue
		if word in STOPWORDS | QTY_WORDS | PRICE_WORDS | TOMAN | RIAL or word.isdigit():
			continue
		if entities.find("warehouse", [word], set()).name:
			continue
		return True
	return False


# ---------------------------------------------------------------- logins
# Read from the text as typed: a password or username keeps its letters' case, dots and signs
PASSWORD_MARKERS = re.compile(r"(?:رمز\s*عبور|رمزعبور|رمزش|رمز|پسوردش|پسورد|گذرواژه|password|pass)", re.I)
USERNAME_MARKERS = re.compile(
	r"(?:نام\s*کاربری|نام‌کاربری|یوزر\s*نیم|یوزرنیم|یوزرش|یوزر|username|user\s*name|user)", re.I
)
LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
SECRET_TOKEN = re.compile(r"[A-Za-z0-9۰-۹٠-٩]")
# Words between a marker and its value: "رمزش رو بذار 1234abcd", "نام کاربری: ali"
FILLER = {"رو", "را", "ش", "اش", "هم", "بذار", "بزار", "بگذار", "باشه", "باشد", "بشه", "کن", "بده", ":", "=", "-", "به", "با", "و", "اون", "این"}


def _after_marker(message, markers, slot_name, token_pattern):
	"""The word after «رمز …» / «نام کاربری …» as typed, or the whole reply when it is one word
	(the answer to the question asked for it)."""
	text = message.text.strip()
	value = None
	for match in markers.finditer(text):
		for token in text[match.end() :].split():
			token = token.strip("«»\"'،,")
			if not token or token in FILLER:
				continue
			if token_pattern.match(token) and SECRET_TOKEN.search(token):
				value = token
			break
		if value:
			break
	# A one-word reply is the answer to the question asked, and only to that one
	if value is None and getattr(message, "answering", None) == slot_name and len(text.split()) == 1 and SECRET_TOKEN.search(text):
		value = text.strip("«»\"'")
	if value is None:
		return None
	# The words read as the marker and the value are not a name
	parts = set(normalize(value).split())
	for i, word in enumerate(message.words):
		if word in parts or markers.fullmatch(word) or word in ("کاربری", "عبور", "نیم"):
			message.used.add(i)
	return value.translate(LATIN_DIGITS)


def _password(message, slot_name):
	return _after_marker(message, PASSWORD_MARKERS, slot_name, re.compile(r"^\S{4,}$"))


def _username(message, slot_name):
	value = _after_marker(message, USERNAME_MARKERS, slot_name, re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{2,}$"))
	return value.lower() if value else None


USER_KINDS = (
	("general_manager", ("مدیر کل", "مدیرکل", "مدیر عامل", "مدیرعامل")),
	("branch_manager", ("مدیر شعبه", "مدیرشعبه", "رئیس شعبه")),
	("accounts_manager", ("مدیر مالی", "مدیرمالی")),
	("accountant", ("حسابدار",)),
	("reception", ("پذیرش",)),
	("sales", ("فروشنده", "کارشناس فروش", "فروش")),
	("customer", ("مشتری",)),
)


def _user_kind(message, slot_name):
	"""What the new login's person does, from words like «حسابدار» or «مدیر شعبه»."""
	text = " " + " ".join(message.words) + " "
	for kind, phrases in USER_KINDS:
		for phrase in phrases:
			if f" {normalize(phrase)} " in text:
				used = set(normalize(phrase).split())
				message.used |= {i for i, w in enumerate(message.words) if w in used}
				return kind
	return None


def _user(message, slot_name):
	"""A login by its name, or by its username or email as typed («kazemi», «ali@example.com»)."""
	found = _entity("user")(message, slot_name)
	if found:
		return found
	from iran_erp.users import find_user

	# As typed: the tokenizer splits «sara.test» at the dot
	for token in message.text.split():
		token = token.strip("«»\"'،,")
		if not re.match(r"^[A-Za-z0-9._@-]{3,}$", token):
			continue
		name = find_user(token)
		if name:
			parts = set(normalize(token).split())
			message.used |= {i for i, w in enumerate(message.words) if w in parts}
			return name
	return None


def _car_spec(message, slot_name):
	from iran_erp.commands.handlers.cars import car_spec

	return car_spec(message.text)


READERS = {
	"car_spec": _car_spec,
	**{kind: _entity(kind) for kind in ENTITY_KINDS},
	"user": _user,
	"party": _party,
	"party_or_account": _party_or_account,
	"doctype": _dictionary(DOCTYPES),
	"report": _dictionary(REPORTS),
	"document": _document,
	"amount": _amount,
	"qty": _qty,
	"number": _number,
	"percent": _percent,
	"limit": _limit,
	"date": _date,
	"period": _period,
	"mobile": _mobile,
	"city": _city,
	"name": _name,
	"text": _text,
	"vat": _vat,
	"payment_mode": _payment_mode,
	"items": _items,
	"password": _password,
	"username": _username,
	"user_kind": _user_kind,
}

# The order slots are read in: names and lists first, since they may contain numbers of their own
ORDER = [
	"document",
	"customer",
	"supplier",
	"party",
	"party_or_account",
	"bank_account",
	"items",
	"item",
	"warehouse",
	"cash_account",
	"account",
	"project",
	"employee",
	"lead",
	"investor",
	"user",
	"branch",
	"user_kind",
	"password",
	"username",
	"doctype",
	"report",
	"mobile",
	"percent",
	"payment_mode",
	"vat",
	"period",
	"date",
	"amount",
	"qty",
	"limit",
	"number",
	"city",
	"name",
	"text",
]
