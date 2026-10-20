"""What shape of answer a request asks for, apart from its subject and its filters:

- output: "one" (a single record, or the few tied for first), "top" (the first few of a ranking),
  "all" (the whole list, only when the user says «همه», «فهرست کامل» and the like), "count", or
  "summary" (the default: totals and the latest few);
- order: what the ranking is by: "longest" (longest in the lot / oldest entry), "newest",
  "price_high", "price_low";
- limit: a number the user gave («۵ تا»);
- group_by: «هر شعبه», «به تفکیک مدل», ...

Handlers put the shape into the request's details, so the trace shows what was understood and the
same shape decides what the tool returns.
"""

import re

from iran_erp.commands.text import normalize, tokens

ALL = ("همه", "همه ی", "همگی", "تمام", "تمامی", "کل", "فهرست کامل", "لیست کامل", "همشون", "همه شون", "همه رو", "همه را")
COUNT = ("چند تا", "چندتا", "تعداد", "چند دستگاه", "چند عدد")
ORDERS = (
	(
		"longest",
		(
			"قدیمی ترین",
			"قدیمی تر",
			"بیشترین زمان",
			"بیشترین مدت",
			"طولانی ترین",
			"بیشتر از همه",
			"زمان زیادی",
			"مدت زیادی",
			"خیلی وقته",
			"خیلی مونده",
			"خوابیده",
			"رسوب",
			"دیر فروش",
			"کندترین",
			"مدت حضور",
			"مدت توقف",
			"روز در پارکینگ",
			"روز در نمایشگاه",
			"خاک می خورن",
			"خاک میخورن",
		),
	),
	("newest", ("جدیدترین", "جدید ترین", "تازه ترین", "اخرین", "آخرین", "تازه رسیده", "تازه پذیرش")),
	("price_high", ("گران ترین", "گرون ترین", "گرانترین", "گرونترین", "بالاترین قیمت", "بیشترین قیمت")),
	("price_low", ("ارزان ترین", "ارزون ترین", "ارزانترین", "ارزونترین", "کمترین قیمت", "پایین ترین قیمت")),
)
GROUPS = (
	("branch", ("هر شعبه", "تفکیک شعبه", "به تفکیک شعبه", "شعبه به شعبه", "بر اساس شعبه", "براساس شعبه", "شعبه ها", "همه شعبه", "شعبه هامون")),
	("model", ("هر مدل", "تفکیک مدل", "به تفکیک مدل", "بر اساس مدل", "مدل به مدل")),
	("status", ("هر وضعیت", "تفکیک وضعیت", "به تفکیک وضعیت", "بر اساس وضعیت")),
	("owner", ("تفکیک مالک", "به تفکیک مالک", "بر اساس مالک", "هر مالک")),
)
# Words for one thing, and for many: «قدیمی‌ترین ماشین کدومه» asks for one, «ماشین‌هایی که ...» for a list
PLURAL = ("ها", "هایی", "های", "هاشون", "هامون", "ا", "ای")
LIST_WORDS = ("لیست", "فهرست", "لیستشو", "لیستش")
ONE_WORDS = ("کدومه", "کدام است", "کدوم است", "کدامه", "کدومشه", "کدوم ماشینه", "کدوم خودروه")
DEFAULT_TOP = 10


def _hay(text: str) -> str:
	"""The message as words, the way the phrases above are compared: once as typed, once joined."""
	return f" {normalize(text)} | {' '.join(tokens(text))} "


def _has(hay: str, phrases) -> bool:
	return any(f" {normalize(p)} " in hay or f" {' '.join(tokens(p))} " in hay for p in phrases)


def _plural(text: str, nouns) -> bool:
	"""Whether the request speaks of several of `nouns` («ماشین‌ها», «خودروهایی که»)."""
	words = normalize(text).split()
	for i, word in enumerate(words):
		for noun in nouns:
			if word == noun and i + 1 < len(words) and words[i + 1] in PLURAL:
				return True
			if word.startswith(noun) and word[len(noun):] in PLURAL:
				return True
	return False


def shape(text: str, nouns=("ماشین", "خودرو", "ماشینا")) -> dict:
	hay = _hay(text)
	out = {}
	order = next((name for name, phrases in ORDERS if _has(hay, phrases)), None)
	if order:
		out["order"] = order
	group = next((name for name, phrases in GROUPS if _has(hay, phrases)), None)
	if group:
		out["group_by"] = group
	limit = next((int(n) for n in re.findall(r"(?<!\d)(\d{1,3})\s*(?:تا|تای|دستگاه|عدد|مورد|اول)", normalize(text))), None)
	if limit:
		out["limit"] = limit
	# «بیشتر از همه» ranks; it does not ask for everything
	rest = hay
	for _name, phrases in (*ORDERS, *GROUPS):
		for p in phrases:
			rest = rest.replace(f" {normalize(p)} ", " ").replace(f" {' '.join(tokens(p))} ", " ")
	if _has(rest, ALL) and not group:
		out["output"] = "all"
	elif _has(hay, COUNT):
		out["output"] = "count"
	elif order:
		many = _plural(text, nouns) or _has(hay, LIST_WORDS) or bool(limit)
		out["output"] = "top" if many and not _has(hay, ONE_WORDS) else "one"
	return out
