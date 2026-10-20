"""The request read as a frame, before and beside the sample sentences:

- subject: what it is about («car», «sales», «account», «invoice», «document»),
- entities: a person or company on record (party), a document by its full name, a car by its model,
  year or colour, a branch; and a person named who is not on record,
- shape: one record, a ranking, a grouping, a count, or everything (query.shape),
- refers: a follow-up of the previous answer: «more» (دیگه چی، بعدی)، «all» (همه)، «same» (همون).

route() turns a frame into one of the registered capabilities with its details, when the frame
says more than the sample sentences do: «لیست ماشین‌ها بر اساس هر شعبه» is about cars, grouped by
branch, though «هر شعبه» is worded like the sales report's samples. The AI reader (understand.py)
answers in the same terms, and only with capability ids from the catalog.
"""

import re

from iran_erp.commands import slots as slot_readers
from iran_erp.commands.query import shape
from iran_erp.commands.text import normalize, tokens

MORE = ("دیگه چی", "دیگه", "دیگه چیا", "بعدی", "بعدیا", "بعدی ها", "بیشتر", "ادامه", "ادامش", "ادامه بده", "بقیه", "بقیش", "بقیه اش", "بازم", "باز هم", "چندتای دیگه", "چند تای دیگه", "موارد بعدی", "صفحه بعد", "بعدیش")
ALL = ("همه", "همشون", "همه شون", "همه رو", "همه را", "همه اش", "همش", "کامل", "فهرست کامل", "لیست کامل", "تمامش")
SAME = ("همون", "همان", "همین", "اونم", "همونو", "همینو", "همون رو")
CAR_WORDS = ("ماشین", "ماشینا", "ماشینها", "ماشینهایی", "خودرو", "خودروها", "خودروهای", "خودروهایی", "ماشینای", "ماشینهای")
# «فروش» as the measure; «آماده فروش» and «فروخته شده» are a car's state
SALES_WORDS = ("فروش", "فروختیم", "فروخته ایم", "فروشمون", "فروش ها")
SALES_STATES = ("اماده فروش", "آماده فروش", "فروخته شده", "فروش رفته")
ACCOUNT_WORDS = ("حساب", "حسابش", "حسابشو", "حسابشون", "حسابو", "صورتحساب", "صورت حساب", "ریز حساب", "گردش حساب", "مانده", "بدهی", "طلب", "بدهکار", "بستانکار", "بدهکاره", "بستانکاره")
ASKS_HOW_MUCH = ("چقدر", "چقد", "مانده", "بدهکار", "بستانکار", "بدهکاره", "بستانکاره", "طلب")
PRINT_WORDS = ("چاپ", "پرینت", "نسخه چاپی")
INFO_WORDS = ("مبلغ", "وضعیت", "چقدره", "جمع")
# A document by its full name: ACC-JV-2026-00012, ACC-SINV-2026-00006, CAR-00021, INS-2026-00003
DOCUMENT_NAME = re.compile(r"^[A-Za-z]{2,6}(-[A-Za-z]{2,6})?-\d{4}(-\d{1,6})?$|^[A-Za-z]{2,6}-\d{3,6}$")
# The capabilities each subject is answered by
SUBJECT_INTENTS = {
	"car": {"car_stock", "car_search", "car_aging"},
	"sales": {"sales_total", "sales_by_branch", "top_customers", "top_items", "item_sales", "last_sales_invoices"},
	"account": {"balance", "party_statement", "receivables", "payables", "party_info", "last_sales_invoices", "last_purchase_invoices", "sales_total", "purchases_total", "invoice_info"},
}


def _hay(text) -> str:
	return f" {normalize(text)} | {' '.join(tokens(text))} "


def _has(hay, phrases) -> bool:
	return any(f" {normalize(p)} " in hay or f" {' '.join(tokens(p))} " in hay for p in phrases)


def refers(question: str) -> str | None:
	"""A short message that only continues the previous answer."""
	text = normalize(question).replace("؟", "").strip()
	words = text.split()
	if not words or len(words) > 4:
		return None
	hay = f" {text} "
	if _has(hay, MORE):
		return "more"
	if text in {normalize(w) for w in ALL}:
		return "all"
	if _has(hay, SAME):
		return "same"
	return None


def documents(question: str) -> list[str]:
	"""Full document names in the message, as typed («ACC-JV-2026-01186»)."""
	return [w.strip("«»\"'.,؟?") for w in str(question).split() if DOCUMENT_NAME.match(w.strip("«»\"'.,؟?"))]


def read(question: str) -> dict:
	hay = _hay(question)
	frame = {"shape": shape(question), "entities": {}}
	rest = hay
	for phrase in SALES_STATES:
		rest = rest.replace(f" {normalize(phrase)} ", " ")
	if _has(rest, SALES_WORDS):
		frame["subject"] = "sales"
	elif _has(hay, CAR_WORDS) or _plural_car(question):
		frame["subject"] = "car"
	elif _has(hay, ACCOUNT_WORDS):
		frame["subject"] = "account"
	names = documents(question)
	if names:
		frame["entities"]["document"] = names[0]
	message = slot_readers.Message(question)
	try:
		party = slot_readers.extract("party", message, "party")
	except slot_readers.Ambiguous as e:
		party = {"options": [label for _v, label in e.options]}
	if party:
		frame["entities"]["party"] = party
	from iran_erp.commands.handlers.cars import car_spec

	spec = car_spec(question) if frame.get("subject") in ("car", None) else None
	if spec:
		frame["entities"]["car"] = spec
	frame["asks_how_much"] = _has(hay, ASKS_HOW_MUCH)
	frame["print"] = _has(hay, PRINT_WORDS)
	frame["info"] = _has(hay, INFO_WORDS)
	return frame


def _plural_car(question) -> bool:
	return any(w.startswith(("ماشین", "خودرو")) for w in tokens(question))


def route(frame: dict, ranked: list) -> tuple[str, dict, str] | None:
	"""(capability, details, the rule) when the frame decides better than the samples, else None."""
	best = ranked[0][0] if ranked else None
	subject = frame.get("subject")
	entities = frame["entities"]
	result = frame["shape"]

	# A document named in full: that document, not the list of its kind
	if entities.get("document") and best not in ("invoice_info",):
		from iran_erp.commands.handlers import document_of

		value = document_of(entities["document"])
		if value:
			if frame["print"]:
				return "print_document", {"document": value}, "document named, to print"
			if frame["info"] and value.split(":")[0] in ("Sales Invoice", "Purchase Invoice"):
				return "invoice_info", {"document": value}, "document named, its amount or state"
			return "open_document", {"document": value}, "document named"

	# About cars: the shape says which of the car capabilities, whatever the samples matched
	if subject == "car":
		if result.get("group_by"):
			return "car_stock", {}, "cars, grouped"
		if result.get("order") == "longest":
			return "car_aging", {}, "cars, by time in the lot"
		if best not in SUBJECT_INTENTS["car"]:
			if entities.get("car"):
				return "car_search", {}, "a car named"
			if not ranked or ranked[0][1] < 0.6:
				return "car_stock", {}, "cars"
	if subject == "sales" and result.get("group_by") == "branch" and best != "sales_by_branch":
		return "sales_by_branch", {}, "sales, by branch"

	# A person or company on record, and their account
	party = entities.get("party")
	# Only when the samples are not sure: «۵ میلیون به حساب بانک واریز کرد» is a payment, well matched
	# («حساب آقای کریمی» names a person's account, not the chart of accounts list)
	sure = bool(ranked) and ranked[0][1] >= 0.5 and best not in ("open_list", "new_document", "open_report")
	if party and subject == "account" and best not in SUBJECT_INTENTS["account"] and not sure:
		intent = "balance" if frame["asks_how_much"] else "party_statement"
		return intent, {}, "a party's account"
	return None
