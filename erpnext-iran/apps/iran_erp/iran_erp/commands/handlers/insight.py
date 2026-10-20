"""Read-only answers built from the ERP's own records: an investor's file, the cars in the lot, and
the statement of every customer (or supplier) at once. Each says what it looked at (the defaults
it took) and links to the record, list or report it comes from."""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import flt

from iran_erp.commands.engine import NeedSlot
from iran_erp.commands.handlers import (
	company,
	jdate,
	link,
	list_url,
	money,
	number,
	period_or,
	report_url,
	require,
	table,
)
from iran_erp.commands.text import normalize

HONORIFICS = {"آقای", "اقای", "آقا", "اقا", "خانم", "جناب", "سرکار", "دکتر", "مهندس"}


# ---------------------------------------------------------------- investors


def find_investors(text: str) -> list[dict]:
	"""Investors whose name has every word typed (honorifics aside), by name or by their supplier."""
	words = [w for w in normalize(text).split() if w not in HONORIFICS and len(w) > 1]
	if not words:
		return []
	conditions = " and ".join(["replace(replace(full_name, 'ي', 'ی'), 'ك', 'ک') like %s"] * len(words))
	return frappe.db.sql(
		f"select name, full_name, mobile from `tabIran Investor` where {conditions} order by full_name limit 10",
		[f"%{w}%" for w in words],
		as_dict=True,
	)


def investor_info(context):
	require("Iran Investor")
	name = context.get("investor")
	typed = (context.get("name") or "").strip()
	if not name and typed:
		found = find_investors(typed)
		if len(found) == 1:
			name = found[0].name
		elif found:
			raise NeedSlot(
				"investor",
				_("More than one investor has this name; which one?"),
				[(r.name, f"{r.full_name} ({r.mobile or r.name})") for r in found],
			)
		else:
			return {
				"answer": _("No investor named «{0}» was found.").format(typed)
				+ " "
				+ _("Check the spelling, or register them."),
				"actions": [
					link(_("Investors"), list_url("Iran Investor")),
					link(_("New Investor"), f"/desk/iran-investor/new?full_name={quote(typed)}"),
				],
			}
	if not name:
		return _all_investors()
	return _one_investor(name)


def _one_investor(name):
	from iran_erp.business.investor_portal import get_my_account

	doc = frappe.get_doc("Iran Investor", name)
	data = get_my_account(investor=name)["investors"][0]
	t = data["totals"]
	username = frappe.db.get_value("User", doc.user, "username") if doc.user else None
	lines = [f"**{doc.full_name}** ({doc.name})", ""]
	for label, value in (
		(_("Mobile"), doc.mobile),
		(_("National ID"), doc.national_id),
		(_("IBAN"), doc.iban),
		(_("Login"), username or doc.user or _("None yet")),
	):
		if value:
			lines.append(f"- {label}: {value}")
	lines += [
		"",
		f"- {_('Active capital')}: {money(t['invested'])}",
		f"- {_('Profit earned to date')}: {money(t['earned'])}",
		f"- {_('Paid to them so far')}: {money(t['paid'])}",
		f"- {_('Still owed to them (profit and capital)')}: {money(t.get('remaining', t['upcoming']))}",
	]
	if data.get("next_payment"):
		p = data["next_payment"]
		lines.append(f"- {_('Next payment')}: {jdate(p['due_date'])} — {money(p['amount'])}")
	if data["contracts"]:
		lines += [
			"",
			table(
				[_("Contract"), _("Amount"), _("From"), _("To"), _("Monthly Rate"), _("Status")],
				[
					[
						f"[{c['name']}](/desk/iran-investment-contract/{c['name']})",
						money(c["amount"]),
						jdate(c["start_date"]),
						jdate(c["end_date"]),
						f"{number(c['monthly_rate'])}٪",
						_(c["status"]),
					]
					for c in data["contracts"]
				],
			),
		]
	else:
		lines += ["", _("No contracts yet.")]
	return {
		"answer": "\n".join(lines),
		"actions": [
			link(_("Investor's file"), f"/desk/iran-investor/{name}"),
			link(_("Investor's Account"), f"/desk/iran-my-account?investor={name}"),
			link(_("Contracts"), list_url("Iran Investment Contract", {"investor": name})),
		],
	}


def _all_investors():
	"""No investor named: every investor with their active money, in one table."""
	rows = frappe.db.sql(
		"""select i.name, i.full_name,
			sum(if(c.docstatus = 1 and c.status in ('Active', 'Matured'), c.amount, 0)) as active,
			count(c.name) as contracts
		from `tabIran Investor` i left join `tabIran Investment Contract` c on c.investor = i.name
		group by i.name order by active desc limit 20""",
		as_dict=True,
	)
	if not rows:
		return {"answer": _("No investors are registered yet."), "actions": [link(_("New Investor"), "/desk/iran-investor/new")]}
	return {
		"answer": _("All investors (no name was given):")
		+ "\n\n"
		+ table(
			[_("Investor"), _("Active capital"), _("Contracts")],
			[[f"[{r.full_name}](/desk/iran-investor/{r.name})", money(r.active), number(r.contracts)] for r in rows],
		),
		"actions": [link(_("Investors"), list_url("Iran Investor"))],
	}


# ---------------------------------------------------------------- cars in the lot

LOT = ("Awaiting Delivery", "In Preparation", "Ready for Sale", "Reserved")
OWNER_WORDS = (
	("Customer", ("امانی", "امانت")),
	("Investor", ("سرمایه گذار", "سرمایه گذاران", "سرمایهگذار")),
	("Business", ("خود نمایشگاه", "متعلق به نمایشگاه", "دارایی", "ملکی", "خودمون", "خودمان")),
)


def car_stock(context):
	"""The cars in the lot: how many, in what state, whose, and what they are worth."""
	require("Iran Vehicle")
	from iran_erp.iran_dealership.dashboard import can_see_books

	text = " " + normalize(context.message.text) + " "
	filters = {"status": ["in", list(LOT)]}
	said = []
	ownership = next((o for o, words in OWNER_WORDS if any(f" {normalize(w)} " in text for w in words)), None)
	if ownership:
		filters["ownership"] = ownership
		said.append(_(ownership))
	if " اماده " in text and " فروش " in text:
		filters["status"] = "Ready for Sale"
		said.append(_("Ready for Sale"))
	branch = context.get("branch")
	if branch:
		filters["branch"] = branch
		said.append(branch)
	cars = frappe.get_list(
		"Iran Vehicle",
		filters=filters,
		fields=["name", "title", "car_model", "year", "color", "status", "branch", "ownership", "asking_price", "entry_date"],
		order_by="entry_date desc, creation desc",
		limit_page_length=0,
	)  # fmt: skip
	scope = "، ".join(said) if said else _("every branch, every owner")
	if not cars:
		return {
			"answer": _("No cars in the lot ({0}).").format(scope),
			"actions": [link(_("Cars"), list_url("Iran Vehicle"))],
		}
	by = lambda key: {k: sum(1 for c in cars if c[key] == k) for k in dict.fromkeys(c[key] for c in cars)}  # noqa: E731
	lines = [_("Cars in the lot ({0}): {1}").format(scope, number(len(cars))), ""]
	lines.append("- " + "، ".join(f"{_(s)}: {number(n)}" for s, n in by("status").items()))
	lines.append("- " + "، ".join(f"{_(o)}: {number(n)}" for o, n in by("ownership").items()))
	branches = by("branch")
	if len(branches) > 1:
		lines.append("- " + "، ".join(f"{b or _('No branch set')}: {number(n)}" for b, n in branches.items()))
	if can_see_books():
		lines.append("- " + _("Asking prices in total: {0}").format(money(sum(flt(c.asking_price) for c in cars))))
	shown = cars[:15]
	lines += [
		"",
		table(
			[_("Car"), _("Year"), _("Color"), _("Status"), _("Asking Price")],
			[
				[
					f"[{c.car_model or c.title}](/desk/iran-vehicle/{c.name})",
					c.year or "",
					c.color or "",
					_(c.status),
					money(c.asking_price),
				]
				for c in shown
			],
		),
	]
	if len(cars) > len(shown):
		lines.append(_("The newest {0} of {1}; the list has them all.").format(number(len(shown)), number(len(cars))))
	list_filters = {k: v for k, v in filters.items()}
	return {
		"answer": "\n".join(lines),
		"actions": [
			link(_("Cars in the lot"), list_url("Iran Vehicle", list_filters)),
			link(_("Dealership dashboard"), "/desk/iran-dealership"),
		],
	}


def has_cars() -> bool:
	return bool(frappe.db.table_exists("Iran Vehicle") and frappe.db.count("Iran Vehicle"))


# ---------------------------------------------------------------- everyone's statement

PLURAL_WORDS = {"مشتریان", "مشتری‌ها", "مشتریها", "مشتریا", "همه", "همشون", "همه‌شون", "کل", "تامین‌کنندگان", "تامینکنندگان"}


def wants_everyone(context) -> bool:
	if context.get("party") == "*":
		return True
	words = set(normalize(context.message.text).split())
	return bool(words & {normalize(w) for w in PLURAL_WORDS})


def all_statements(context):
	"""Every customer's (or supplier's) movements in the period and balance today."""
	require("GL Entry")
	text = normalize(context.message.text)
	party_type = "Supplier" if ("تامین" in text or "فروشنده" in text) else "Customer"
	start, end, label = period_or(context, "year")
	rows = frappe.db.sql(
		"""select party,
			sum(if(posting_date between %(start)s and %(end)s, debit, 0)) as debit,
			sum(if(posting_date between %(start)s and %(end)s, credit, 0)) as credit,
			sum(debit - credit) as balance
		from `tabGL Entry`
		where company = %(company)s and party_type = %(party_type)s and is_cancelled = 0
		group by party having debit or credit or abs(balance) >= 1
		order by abs(sum(debit - credit)) desc limit 25""",
		{"start": start, "end": end, "company": company(), "party_type": party_type},
		as_dict=True,
	)
	field = "customer_name" if party_type == "Customer" else "supplier_name"
	report = "Customer Ledger Summary" if party_type == "Customer" else "Supplier Ledger Summary"
	url = report_url(report, {"company": company(), "from_date": start, "to_date": end})
	who = _("all customers") if party_type == "Customer" else _("all suppliers")
	if not rows:
		return {"answer": _("No transactions for {0} ({1}).").format(who, label), "actions": [link(_(report), url)]}
	names = dict(frappe.get_all(party_type, filters={"name": ["in", [r.party for r in rows]]}, fields=["name", field], as_list=True))
	balance = sum(flt(r.balance) for r in rows)
	answer = (
		_("Statement of {0} ({1}); balance today is in the company's books (debit: they owe us).").format(who, label)
		+ "\n\n"
		+ table(
			[_("Party"), _("Debit"), _("Credit"), _("Balance today")],
			[
				[
					f"[{names.get(r.party, r.party)}]({report_url('General Ledger', {'company': company(), 'party_type': party_type, 'party': frappe.as_json([r.party], indent=None)})})",
					money(r.debit),
					money(r.credit),
					_balance_text(r.balance),
				]
				for r in rows
			],
		)
		+ "\n\n"
		+ _("Total balance: {0}").format(_balance_text(balance))
	)
	return {"answer": answer, "actions": [link(_(report), url)]}


def _balance_text(value) -> str:
	if abs(flt(value)) < 1:
		return money(0)
	return f"{money(abs(value))} {_('Dr') if value > 0 else _('Cr')}"
