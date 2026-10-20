"""Operations understood from the parts of a request, whatever their order, and carried out in the
ERP step by step.

A request is read as
- an action: make («بزن، ثبت کن، درست کن، بساز، تعریف کن، صادر کن، فاکتور کن»), show, open, ...
- a subject: sales invoice, quotation, user, investment, customer, ...
- the people and records it names, by their role: «برای خانم شریفی», «از آقای کریمی», «به ...»,
- the details it gives: items with quantity and price, an amount, a role («نقش مشتری»), a password.

parse() turns these into an operation of OPERATIONS. Each operation declares the fields it needs,
which are optional and which have defaults. The dialog keeps what is known in the conversation
state and asks only for what is still missing, one question at a time, with a summary of what was
understood. A record named is looked up in the ERP: one match is taken, several are offered to
choose from (only those), none is said, with a way to register it. When everything is known the
operation makes a real ERP draft (or a switched-off login) and links to it; nothing is submitted.

Words are compared after normalize() (ی/ي، ک/ك، half-spaces, punctuation, Persian digits), and the
vocabulary is made of parts (verbs, subjects, role words), not of whole sample sentences.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from iran_erp.commands import entities
from iran_erp.commands import slots as slot_readers
from iran_erp.commands.text import is_cancel, normalize, stem, tokens, yes_no

# ---------------------------------------------------------------- vocabulary, in parts

VERBS = {
	"create": (
		"بزن", "بزنید", "بزنی", "بزنین", "ثبت", "ثبتش", "بساز", "بسازید", "بسازی", "بسازین", "درست", "ایجاد",
		"تعریف", "صادر", "اضافه", "فاکتور کن", "فاکتورش کن", "بنویس برای", "جدید", "باز کن برای",
	),
	"show": ("بیار", "بده", "نشون", "نشان", "ببینم", "لیست", "فهرست", "چیه", "چیا", "کدومه", "چقدر", "چند"),
}
# Words that make a request about creating, even with «بده»: «یه فاکتور بده برای ...» is rare; «بزن» is not
STRONG_CREATE = ("بزن", "بزنید", "بزنی", "بزنین", "ثبت", "ثبتش", "بساز", "بسازید", "بسازی", "درست", "ایجاد", "تعریف", "صادر", "فاکتور کن", "فاکتورش کن")
# Most specific first: «پیش فاکتور» before «فاکتور», «کاربر با نقش مشتری» is a user
SUBJECTS = (
	("quotation", ("پیش فاکتور", "پیشفاکتور", "پیش‌فاکتور")),
	("purchase_invoice", ("فاکتور خرید",)),
	("sales_invoice", ("فاکتور فروش", "صورتحساب فروش")),
	("sales_order", ("سفارش فروش",)),
	("purchase_order", ("سفارش خرید",)),
	("user", ("کاربر", "یوزر", "یوزرنیم", "نام کاربری", "اکانت", "حساب کاربری", "دسترسی ورود", "دسترسی")),
	("investment", ("قرارداد سرمایه گذاری", "سرمایه گذاری", "سرمایه‌گذاری")),
	("investor", ("سرمایه گذار جدید",)),
	("invoice", ("فاکتور",)),
	("receipt", ("دریافت وجه", "دریافتی", "واریزی")),
	("customer", ("مشتری جدید", "مشتری")),
	("supplier", ("تامین کننده جدید", "تامین کننده")),
	("lead", ("سرنخ",)),
	("todo", ("یادآوری", "یاداوری")),
)
# What happened, said in the past: «فروختیم» is a sale, «خریدیم» a purchase, «گرفتیم» money in
CUES = {
	"sold": ("فروختیم", "فروخته ایم", "فروختم", "فروش رفت"),
	"bought": ("خریدیم", "خریدم", "خرید کردیم"),
	"received": ("گرفتیم", "گرفتم", "دریافت کردیم", "داده", "واریز کرده", "واریز کرد", "پرداخت کرده"),
}
# Whom the request names, by the word before them
ROLE_MARKERS = ("برای", "به", "از", "واسه", "واسه ی", "برا")
# The operations the parts make; a subject the action does not make here is left to the commands
OPERATIONS_BY_PARTS = {
	("create", "sales_invoice"): "sell",
	("create", "invoice"): "sell",
	("create", "user"): "user",
	("create", "investment"): "invest",
	("create", "quotation"): "create_quotation",
	("create", "sales_order"): "create_sales_order",
	("create", "purchase_invoice"): "create_purchase_invoice",
	("create", "purchase_order"): "create_purchase_order",
	("create", "customer"): "create_customer",
	("create", "supplier"): "create_supplier",
	("create", "investor"): "create_investor",
	("create", "lead"): "create_lead",
	("create", "todo"): "create_todo",
	("create", "receipt"): "receive_payment",
}
ACCOUNT_FIELDS = ("received_to", "paid_to")


def _hay(text) -> str:
	return f" {normalize(text)} | {' '.join(tokens(text))} "


def _has(hay, phrases) -> bool:
	return any(f" {normalize(p)} " in hay or f" {' '.join(tokens(p))} " in hay for p in phrases)


def vocabulary() -> set[str]:
	"""Stems of every word of the vocabulary: they are how people ask, never a name or an item."""
	words = set()
	for phrases in (*VERBS.values(), *(p for _s, p in SUBJECTS), *CUES.values(), ROLE_MARKERS):
		for phrase in phrases:
			words |= {stem(w) for w in tokens(phrase)}
	words |= {stem(w) for w in tokens("کالا محصول جنس نقش با و هم یک یه جدید براش برایش بهم اطلاع لطفا بابت مبلغ")}
	return words


# ---------------------------------------------------------------- reading a request


def parse(question: str) -> dict | None:
	"""{"operation", "action", "subject", "cues", "found"} of a request, or None when its parts do
	not make an operation here."""
	hay = _hay(question)
	cues = [name for name, phrases in CUES.items() if _has(hay, phrases)]
	action = "create" if _has(hay, STRONG_CREATE) else ("show" if _has(hay, VERBS["show"]) else None)
	subject = next((name for name, phrases in SUBJECTS if _has(hay, phrases)), None)
	# «ما به خانم شریفی کالا فروختیم؛ فاکتور کن», «۲ میلیارد از ... بابت سرمایه‌گذاری گرفتیم ثبتش کن»
	if subject == "invoice" and "bought" in cues:
		subject = "purchase_invoice"
	if subject == "invoice" and "sold" in cues:
		subject = "sales_invoice"
	if subject is None and "sold" in cues and action == "create":
		subject = "sales_invoice"
	if subject == "customer" and _has(hay, ("کاربر", "یوزر", "نام کاربری", "پسورد", "رمز")):
		subject = "user"
	# A login for an investor opens on their own account: that is its own command
	if subject in ("user", "investment") and _has(hay, ("سرمایه گذار", "سرمایه‌گذار")) and _has(
		hay, ("دسترسی", "کاربر", "یوزر", "یوزرنیم", "پسورد", "رمز", "لاگین", "نام کاربری")
	):
		return {"operation": "create_investor_login", "action": action, "subject": "user", "cues": cues} if action == "create" else None
	if action != "create" or not subject:
		return None
	operation = OPERATIONS_BY_PARTS.get((action, subject))
	if not operation:
		return None
	return {"operation": operation, "action": action, "subject": subject, "cues": cues}


def _message(question):
	from iran_erp.commands.engine import _keywords

	keywords = {stem(w) for w in vocabulary()}
	return slot_readers.Message(question, keywords | _keywords("create_sales_invoice"))


# ---------------------------------------------------------------- finding records


def find(kind: str, text: str, message=None) -> dict:
	"""A record of `kind` named in the text: {"name", "label"} for one, {"options"} for several,
	{"named"} when no record has the name said («خانم شریفی»), or {} when nothing names one."""
	message = message or _message(text)
	found = entities.find(kind, message.words, message.blocked())
	if found and not found.asked:
		message.used |= found.used
		return {"name": found.name, "label": found.label}
	if found.options and not found.asked:
		message.used |= found.used
		return {"options": found.options}
	named = slot_readers.person_phrase(message, stop=vocabulary())
	if found.asked or named:
		said = found.asked or named[1]
		if named:
			message.used |= named[0]
		else:
			message.used |= found.used
		similar = list(found.options)
		for word in [w for w in tokens(said) if w not in entities.HONORIFICS]:
			near = entities.find(kind, [word])
			similar += [(near.name, near.label)] if near else list(near.options)
		return {"named": said, "options": list(dict.fromkeys(similar))[:6]}
	return {}


def _pick(text, options):
	from iran_erp.commands.engine import _pick as pick

	return pick(text, options)


# ---------------------------------------------------------------- the operations

DOCTYPE_OF = {"customer": "Customer", "investor": "Iran Investor", "item": "Item", "supplier": "Supplier"}


def _account_options():
	from iran_erp.commands.handlers import company

	rows = frappe.get_list(
		"Account",
		filters={"company": company(), "is_group": 0, "disabled": 0, "account_type": ["in", ["Cash", "Bank"]]},
		fields=["name", "account_name", "account_type"],
		order_by="account_type desc, account_name",
		limit=12,
	)
	return [(r.name, r.account_name) for r in rows]


def _vat_template():
	from iran_erp.commands.handlers import company

	return frappe.db.get_value("Sales Taxes and Charges Template", {"company": company(), "is_default": 1, "disabled": 0})


def _price(item):
	return flt(frappe.db.get_value("Item Price", {"item_code": item, "price_list": "Standard Selling"}, "price_list_rate"))


class Ask(Exception):
	"""The next question: what to ask, about which field, with which answers to offer."""

	def __init__(self, field, question, options=None, pick=None, replies=None, actions=None):
		super().__init__(question)
		self.field, self.question, self.options = field, question, options or []
		self.pick, self.replies, self.actions = pick, replies or [], actions or []


def _party(op, known, kind, title, question):
	"""The customer (investor, ...) of the operation: found, chosen, or said not to be on record."""
	value = known.get(kind)
	if value and not isinstance(value, dict):
		return value
	pending = value if isinstance(value, dict) else {}
	if pending.get("named"):
		raise Ask(
			kind,
			_("No {0} named «{1}» is on record.").format(title, pending["named"])
			+ (" " + _("Did you mean one of these?") if pending.get("options") else "")
			+ " "
			+ _("Write another name, or register «{0}».").format(pending["named"]),
			pending.get("options"),
			pick={"doctype": DOCTYPE_OF[kind]},
			replies=[{"label": _("Register «{0}» as a new {1}").format(pending["named"], title), "text": f"ثبت {pending['named']}"}],
		)
	if pending.get("options"):
		raise Ask(kind, _("More than one {0} has this name; which one?").format(title), pending["options"], pick={"doctype": DOCTYPE_OF[kind]})
	raise Ask(kind, question, pick={"doctype": DOCTYPE_OF[kind]})


def _summary_sell(known) -> str:
	parts = [_("Sales invoice for {0}").format(known.get("customer_label") or "…")]
	for line in known.get("lines") or []:
		parts.append(f"{line['label']} × {_number(line['qty'])}" + (f" ({_money(line['rate'])})" if line.get("rate") else ""))
	return "، ".join(parts)


def _number(value):
	from iran_erp.commands.handlers import number

	return number(value)


def _money(value):
	from iran_erp.commands.handlers import money

	return money(value)


def step_sell(op):
	"""A sales invoice: customer, items (with quantity and price), VAT, whether it was paid."""
	known = op["known"]
	customer = _party(op, known, "customer", _("customer"), _("For which customer is the invoice?"))
	known.setdefault("customer_label", frappe.db.get_value("Customer", customer, "customer_name") or customer)
	lines = known.setdefault("lines", [])
	if not known.get("line") and known.get("queue"):
		known["line"] = known["queue"].pop(0)
	line = known.get("line")
	if line:
		if not line.get("qty_said"):
			raise Ask("qty", _("How many «{0}»?").format(line["label"]), replies=[{"label": "۱", "text": "1"}, {"label": "۲", "text": "2"}])
		if not line.get("rate"):
			price = _price(line["item"])
			if price:
				line["rate"] = price
				line["rate_from_list"] = True
			else:
				raise Ask("rate", _("What is the price of each «{0}»? (rials, or say «تومان»)").format(line["label"]))
		lines.append(line)
		known["line"] = None
		if known.get("queue"):
			return step_sell(op)
		known["more"] = None
	if not lines:
		raise Ask(
			"item",
			_("I am preparing a sales invoice for {0}. Which product?").format(known["customer_label"]),
			pick={"doctype": "Item", "filters": {"disabled": 0, "is_sales_item": 1}},
		)
	if known.get("more") is None:
		raise Ask(
			"more",
			_summary_sell(known) + "\n\n" + _("Another item? (write it, or «نه»)"),
			replies=[{"label": _("No, that is all"), "text": "نه"}],
			pick={"doctype": "Item", "filters": {"disabled": 0, "is_sales_item": 1}},
		)
	if known.get("vat") is None and _vat_template():
		raise Ask("vat", _("Add value added tax to this invoice?"), replies=[{"label": _("Yes, with VAT"), "text": "بله"}, {"label": _("No VAT"), "text": "نه"}])
	if known.get("paid") is None:
		raise Ask("paid", _("Has anything been paid for this invoice?"), replies=[{"label": _("Yes"), "text": "بله"}, {"label": _("No"), "text": "نه"}])
	if known["paid"]:
		if known.get("paid_amount") is None:
			raise Ask("paid_amount", _("How much was paid? (or «همه» for the whole invoice)"), replies=[{"label": _("All of it"), "text": "همه"}])
		if not known.get("paid_to"):
			raise Ask("paid_to", _("Into which cash box or bank account?"), _account_options())
	return run_sell(op)


def run_sell(op):
	from iran_erp.ai import tools
	from iran_erp.commands.handlers import company, doc_link

	known = op["known"]
	result = tools.create_sales_invoice_draft(
		customer=known["customer"],
		items=[{"item_code": l["item"], "qty": l["qty"], "rate": l.get("rate")} for l in known["lines"]],
		apply_vat=bool(known.get("vat")) if _vat_template() else None,
		company=company(),
	)
	if result.get("error"):
		frappe.throw(result["error"])
	invoice = frappe.get_doc("Sales Invoice", result["name"])
	from iran_erp.commands.handlers.selling import _summary

	lines = [_("Draft sales invoice {0} for {1}:").format(invoice.name, invoice.customer_name), "", _summary(invoice)]
	if any(l.get("rate_from_list") for l in known["lines"]):
		lines.append(_("Prices not said were taken from the price list."))
	actions = [doc_link("Sales Invoice", invoice.name)]
	if known.get("paid"):
		amount = invoice.grand_total if known["paid_amount"] == "all" else flt(known["paid_amount"])
		payment = _draft_receipt(invoice, amount, known["paid_to"])
		lines += ["", _("Draft receipt {0}: {1} into {2}. Submit the invoice first, then the receipt, and allocate it to the invoice.").format(payment.name, _money(amount), frappe.db.get_value("Account", known["paid_to"], "account_name"))]
		actions.append(doc_link("Payment Entry", payment.name))
	lines += ["", _("Nothing is final: review the drafts in the ERP and submit them there.")]
	return {"answer": "\n".join(lines), "actions": actions}


def _draft_receipt(invoice, amount, account):
	from erpnext.accounts.party import get_party_account

	mode = "Cash" if frappe.get_cached_value("Account", account, "account_type") == "Cash" else "Wire Transfer"
	doc = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"company": invoice.company,
			"posting_date": nowdate(),
			"mode_of_payment": mode if frappe.db.exists("Mode of Payment", mode) else None,
			"party_type": "Customer",
			"party": invoice.customer,
			"paid_from": get_party_account("Customer", invoice.customer, invoice.company),
			"paid_to": account,
			"paid_amount": amount,
			"received_amount": amount,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"remarks": _("For sales invoice {0}").format(invoice.name),
		}
	)
	if mode != "Cash":
		doc.reference_no = invoice.name
		doc.reference_date = nowdate()
	doc.insert()
	return doc


def step_user(op):
	"""A customer's login for the portal: tied to that customer, signing in with their email or a
	username; the password is the operator's or set by the customer from an emailed link."""
	known = op["known"]
	if known.get("kind") != "customer":
		raise Reroute("create_user_login")
	customer = _party(op, known, "customer", _("customer"), _("For which customer is the login?"))
	doc = frappe.db.get_value("Customer", customer, ["customer_name", "email_id", "mobile_no"], as_dict=True)
	known.setdefault("customer_label", doc.customer_name)
	if known.get("email") is None:
		known["email"] = (doc.email_id or "").strip().lower() or ""
	existing = frappe.db.get_value("Portal User", {"parent": customer, "parenttype": "Customer"}, "user")
	if existing:
		return {
			"answer": _("{0} already has a portal login ({1}).").format(doc.customer_name, existing),
			"actions": [{"label": existing, "url": f"/desk/user/{existing}"}],
		}
	if not known.get("username"):
		suggested = re.sub(r"[^a-z0-9._-]", "", known["email"].split("@")[0]) if known["email"] else ""
		if len(suggested) >= 3 and not frappe.db.exists("User", {"username": suggested}):
			known["username"] = suggested
		else:
			raise Ask("username", _("{0} has no email on record. Their username? (English letters, for example sara.kazemi)").format(doc.customer_name) if not known["email"] else _("Their username? (English letters)"))
	if known.get("password_way") is None:
		replies = [{"label": _("I will write the password"), "text": "رمز را می‌نویسم"}]
		if known["email"]:
			replies.append({"label": _("Email them a link to set it"), "text": "لینک ایمیل"})
		raise Ask(
			"password_way",
			_("Login for {0} (customer), username «{1}»{2}. How is the password set?").format(
				doc.customer_name, known["username"], (" " + _("or the email {0}").format(known["email"])) if known["email"] else ""
			),
			replies=replies,
		)
	if known["password_way"] == "write" and not _password(op):
		raise Ask("password", _("The password? (at least 6 characters; it is not shown or kept in the chat)"))
	return run_user(op, doc)


def run_user(op, doc):
	from iran_erp.users import create_user

	known = op["known"]
	result = create_user(
		doc.customer_name,
		known["username"],
		_password(op) if known["password_way"] == "write" else None,
		"customer",
		email=known["email"] or None,
		mobile=doc.mobile_no,
		enabled=0,
		customer=known["customer"],
	)
	how = (
		_("the password you gave")
		if known["password_way"] == "write"
		else _("no password yet: once enabled, «Reset Password» on the form emails {0} a link to set one").format(known["email"])
	)
	lines = [
		_("A portal login for {0} is ready, switched off. It is tied to this customer, so it shows only their own orders and invoices.").format(doc.customer_name),
		"",
		f"- {_('Username')}: {result['username']}" + (f" ({_('or')} {known['email']})" if known["email"] else ""),
		f"- {_('Password')}: {how}",
		f"- {_('Sign in at')}: {result['login_url']}",
		"",
		_("To let them in, open it and tick «Enabled»."),
	]
	return {"answer": "\n".join(lines), "actions": [{"label": _("Review and enable the login"), "url": f"/desk/user/{result['user']}"}]}


def step_invest(op):
	"""A new investment: investor, amount, length, monthly profit, the account it came into."""
	known = op["known"]
	investor = _party(op, known, "investor", _("investor"), _("From which investor?"))
	known.setdefault("investor_label", frappe.db.get_value("Iran Investor", investor, "full_name"))
	if not known.get("amount"):
		raise Ask("amount", _("How much was invested? (rials, or say «تومان»)"))
	if not known.get("monthly_rate"):
		raise Ask("monthly_rate", _("Investment of {0} from {1}, for {2} months. Monthly profit rate, in percent?").format(_money(known["amount"]), known["investor_label"], _number(known.get("months") or 6)))
	if not known.get("received_to"):
		raise Ask("received_to", _("Into which cash box or bank account did it come?"), _account_options())
	return run_invest(op)


def run_invest(op):
	from iran_erp.commands.handlers import company, doc_link

	known = op["known"]
	doc = frappe.get_doc(
		{
			"doctype": "Iran Investment Contract",
			"investor": known["investor"],
			"contract_type": known.get("contract_type") or "Partnership",
			"start_date": nowdate(),
			"company": company(),
			"scope": "Whole Business",
			"amount": known["amount"],
			"months": known.get("months") or 6,
			"monthly_rate": known["monthly_rate"],
			"received_to": known["received_to"],
		}
	)
	doc.insert()
	lines = [
		_("Draft investment contract {0}: {1} from {2}, {3} months at {4}% a month.").format(
			doc.name, _money(doc.amount), known["investor_label"], _number(doc.months), _number(doc.monthly_rate)
		),
		_("The money is recorded as received when the contract is submitted in the ERP."),
	]
	return {"answer": "\n".join(lines), "actions": [doc_link("Iran Investment Contract", doc.name)]}


class Reroute(Exception):
	def __init__(self, intent):
		super().__init__(intent)
		self.intent = intent


OPERATIONS = {
	"sell": {"title": "فاکتور فروش", "step": step_sell, "party": "customer"},
	"user": {"title": "کاربر پورتال مشتری", "step": step_user, "party": "customer"},
	"invest": {"title": "قرارداد سرمایه‌گذاری", "step": step_invest, "party": "investor"},
}


# ---------------------------------------------------------------- reading details into an operation


def _read_first(op, question):
	"""Everything the first message already says, by role: the party, the items, amounts, a role."""
	known = op["known"]
	message = _message(question)
	spec = OPERATIONS[op["operation"]]
	party = find(spec["party"], question, message)
	if party.get("name"):
		known[spec["party"]] = party["name"]
	elif party:
		known[spec["party"]] = party
	if op["operation"] == "sell":
		try:
			read = slot_readers.extract("items", message, "items") if message.words else None
		except slot_readers.Ambiguous:
			read = None
		if read:
			# Complete lines are kept; the others wait their turn for a quantity or a price
			for line in read.get("lines") or []:
				if line.get("qty_said") and line.get("rate"):
					known.setdefault("lines", []).append(line)
				else:
					known.setdefault("queue", []).append(line)
			if read.get("unknown"):
				known["unknown_items"] = read["unknown"]
		vat = slot_readers.extract("vat", message, "vat")
		if vat:
			known["vat"] = vat == "yes"
	elif op["operation"] == "user":
		# A role said («نقش مشتری», «حسابدار»); without one, the login command asks for it
		known["kind"] = slot_readers.extract("user_kind", slot_readers.Message(question), "kind")
		username = slot_readers.extract("username", slot_readers.Message(question), "username")
		if username:
			known["username"] = username
		password = slot_readers.extract("password", slot_readers.Message(question), "password")
		# «پسورد بساز» asks for one to be made; a password is typed in Latin letters and digits
		if password and password != known.get("username") and re.search(r"[A-Za-z0-9]", password):
			op["password"] = password
			known["password_way"] = "write"
	elif op["operation"] == "invest":
		amount = slot_readers.extract("amount", message, "amount")
		if amount:
			known["amount"] = amount
		months = re.search(r"(\d{1,2})\s*ماه", normalize(question))
		if months:
			known["months"] = int(months.group(1))
		if _has(_hay(question), ("حواله",)):
			known["contract_type"] = "Car Remittance"


def _read_answer(op, field, text) -> str | None:
	"""Put the reply into the field asked; returns a problem to say, or None."""
	known = op["known"]
	options = op.get("options") or []
	kind = OPERATIONS[op["operation"]]["party"]
	if field in ("customer", "investor"):
		chosen = _pick(text, options) if options else None
		doctype = DOCTYPE_OF[field]
		pending = known.get(field) if isinstance(known.get(field), dict) else {}
		if not chosen and frappe.db.exists(doctype, text.strip()):
			chosen = text.strip()
		if not chosen and normalize(text).startswith(normalize("ثبت")):
			# «ثبت خانم شریفی»: the name as written in the reply, or the one asked about
			said = re.sub(r"^\s*ثبت\s*", "", text.strip()).strip() or pending.get("named")
			if said:
				chosen = _register(field, said)
		if not chosen:
			found = find(field, text)
			if found.get("name"):
				chosen = found["name"]
			elif found:
				known[field] = found if found.get("options") or found.get("named") else {"named": text.strip()}
				return None
			else:
				known[field] = {"named": text.strip(), "options": []}
				return None
		known[field] = chosen
		return None
	if field in ("item", "more"):
		if field == "more" and yes_no(text) is False:
			known["more"] = False
			return None
		code = text.strip()
		if frappe.db.exists("Item", code):
			known["line"] = {"item": code, "label": frappe.db.get_value("Item", code, "item_name") or code, "qty": 1, "qty_said": False, "rate": None}
			return None
		if field == "more" and yes_no(text) is True:
			known["more"] = None
			raise Ask("item", _("Which product?"), pick={"doctype": "Item", "filters": {"disabled": 0, "is_sales_item": 1}})
		message = _message(text)
		try:
			read = slot_readers.extract("items", message, "items")
		except slot_readers.Ambiguous as e:
			raise Ask("item", _("Several items have this name; which one?"), e.options, pick={"doctype": "Item"}) from None
		lines = (read or {}).get("lines") or []
		if not lines:
			return _("«{0}» was not found among the items. Write its exact name, or choose from the list.").format(text.strip())
		for line in lines[1:]:
			known.setdefault("lines", []).append(line)
		known["line"] = lines[0]
		return None
	if field == "qty":
		numbers = slot_readers._numbers(slot_readers.Message(text))
		if not numbers or numbers[0].value <= 0:
			return _("Write the quantity as a number.")
		known["line"]["qty"] = numbers[0].value
		known["line"]["qty_said"] = True
		return None
	if field == "rate":
		amount = slot_readers.extract("amount", slot_readers.Message(text), "amount")
		if not amount:
			return _("Write the price as a number, for example 12 میلیون تومان.")
		known["line"]["rate"] = amount
		return None
	if field in ("vat", "paid"):
		answer = yes_no(text) if field == "paid" else slot_readers.extract("vat", slot_readers.Message(text), "vat")
		if answer is None:
			return _("Please answer yes or no.")
		known[field] = answer if field == "paid" else answer == "yes"
		return None
	if field == "paid_amount":
		if normalize(text) in {normalize(w) for w in ("همه", "همش", "کامل", "کل", "تمام")}:
			known["paid_amount"] = "all"
			return None
		amount = slot_readers.extract("amount", slot_readers.Message(text), "amount")
		if not amount:
			return _("Write the amount, or «همه».")
		known["paid_amount"] = amount
		return None
	if field in ACCOUNT_FIELDS:
		chosen = _pick(text, options)
		if not chosen:
			return _("Choose one of the accounts by its number.")
		known[field] = chosen
		return None
	if field == "amount":
		amount = slot_readers.extract("amount", slot_readers.Message(text), "amount")
		if not amount:
			return _("Write the amount as a number.")
		known["amount"] = amount
		return None
	if field == "monthly_rate":
		numbers = slot_readers._numbers(slot_readers.Message(text))
		if not numbers or not 0 < numbers[0].value <= 20:
			return _("Write the monthly profit rate in percent, for example 4.")
		known["monthly_rate"] = numbers[0].value
		return None
	if field == "username":
		from iran_erp.utils.national_id import normalize_digits

		value = normalize_digits(text).strip().lower().replace(" ", "")
		from iran_erp.users import USERNAME

		if not USERNAME.match(value) or frappe.db.exists("User", {"username": value}):
			return _("That username is not usable or is taken; write another (English letters).")
		known["username"] = value
		return None
	if field == "password_way":
		known["password_way"] = "email" if ("ایمیل" in text or "لینک" in text or "email" in text.lower()) else "write"
		return None
	if field == "password":
		if len(text.strip()) < 6:
			return _("The password needs at least 6 characters.")
		op["password"] = text.strip()
		return None
	return None


def _register(kind, name):
	"""A customer or investor said to be registered from the chat («ثبت خانم شریفی»)."""
	if kind == "customer":
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
			}
		).insert()
	else:
		doc = frappe.get_doc({"doctype": "Iran Investor", "full_name": name}).insert()
	entities.forget(kind)
	return doc.name


# ---------------------------------------------------------------- the dialog


def _state(op):
	"""The operation as kept between messages; a password only encrypted with the site's key."""
	from frappe.utils.password import encrypt

	kept = {k: v for k, v in op.items() if k != "password"}
	if op.get("password"):
		kept["password_sealed"] = encrypt(op["password"])
	return {"operation": kept}


def _password(op):
	if op.get("password"):
		return op["password"]
	if op.get("password_sealed"):
		from frappe.utils.password import decrypt

		return decrypt(op["password_sealed"])
	return None


def _go(op):
	"""The next question, or the operation done."""
	from iran_erp.commands.engine import _reply

	spec = OPERATIONS[op["operation"]]
	try:
		result = spec["step"](op)
	except Ask as ask:
		return _ask(op, ask)
	except Reroute as e:
		from iran_erp.commands.engine import _run

		return _run(e.intent, {}, slot_readers.Message(op.get("question") or ""), False)
	reply = _reply(intent=op["operation_intent"], **result)
	reply["trace"] = _trace(op, links=[a.get("url") for a in result.get("actions") or []])
	return reply


def _ask(op, ask):
	"""The question, after what is understood so far (and what went wrong with the last answer)."""
	from iran_erp.commands.engine import _options_text, _reply

	op["asking"], op["options"] = ask.field, ask.options
	op["pick"], op["replies"] = ask.pick, ask.replies
	text = ask.question
	if ask.options:
		text += "\n\n" + _options_text(ask.options) + "\n\n" + _("Reply with the number.")
	if op.get("problem"):
		text = op.pop("problem") + "\n\n" + text
	reply = _reply(text, actions=ask.actions, state=_state(op), intent=op["operation_intent"])
	reply["trace"] = _trace(op, asks=ask.field)
	return reply


def _trace(op, asks=None, links=None) -> dict:
	known = {k: v for k, v in op["known"].items() if k not in ("password", "queue")}
	return {
		"capability": op["operation_intent"],
		"operation": op["operation"],
		"parts": {k: op.get(k) for k in ("action", "subject", "cues")},
		"parameters": known,
		"asks": asks,
		"tool": f"operations.step_{op['operation']}",
		"links": links or [],
		"understood_by": "Composition",
	}


INTENT_OF = {"sell": "create_sales_invoice", "user": "create_customer_login", "invest": "create_investment_contract"}


def start(parsed: dict, question: str) -> dict:
	"""Begin an operation from a request's parts; operations without a dialog of their own go to
	their command, with the details already read."""
	from iran_erp.commands.engine import INTENT_BY_NAME, _keywords, _run

	operation = parsed["operation"]
	if operation not in OPERATIONS:
		if operation not in INTENT_BY_NAME:
			return None
		return _run(operation, {}, slot_readers.Message(question, _keywords(operation)), False)
	op = {**parsed, "known": {}, "question": question, "operation_intent": INTENT_OF[operation]}
	_read_first(op, question)
	if op["known"].pop("unknown_items", None) and not op["known"].get("line") and not op["known"].get("lines"):
		op["problem"] = _("Some of the items you wrote were not found; choose them from the list.")
	return _go(op)


def resume(question: str, state: dict) -> dict | None:
	"""The reply to the question an operation asked; None when it is a new request instead."""
	from iran_erp.commands.engine import _reply

	op = dict(state["operation"])
	op["known"] = dict(op.get("known") or {})
	if is_cancel(question):
		return _reply(_("Cancelled. Nothing was made."))
	# A new request of its own (an operation, or a strong command match) starts over
	parsed = parse(question)
	if parsed and op.get("asking") not in ("item", "more"):
		return None
	try:
		problem = _read_answer(op, op.get("asking"), question)
	except Ask as ask:
		return _ask(op, ask)
	if problem:
		op["problem"] = problem
	return _go(op)


def quick_replies(op: dict) -> dict:
	replies = list(op.get("replies") or [])
	if op.get("options"):
		replies = [{"label": label, "text": str(i)} for i, (_v, label) in enumerate(op["options"], 1)] + replies
	replies.append({"label": _("Cancel"), "text": "انصراف", "cancel": True})
	return {"replies": replies, "pick": op.get("pick")}


def masks_reply(state: dict | None) -> bool:
	"""Whether the next message answers a password question (it is then not stored as typed)."""
	op = (state or {}).get("operation") or {}
	return op.get("asking") == "password" or (state or {}).get("waiting") == "password"
