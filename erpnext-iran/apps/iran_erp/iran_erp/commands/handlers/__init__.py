"""What each chat command does. Every handler gets a Context and returns {"answer", "actions"}.

Handlers run as the user who sent the message: reads go through frappe.get_list or check
permissions first, and anything they create is a draft the user reviews.
"""

import json
from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands.text import today
from iran_erp.utils.jalali import format_jalali, to_jalali

MAX_LINES = 10


def company() -> str:
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def currency_label() -> str:
	code = frappe.db.get_value("Company", company(), "default_currency") or "IRR"
	return {"IRR": "ریال", "IRT": "تومان"}.get(code, code)


def money(value) -> str:
	"""1234567 -> ۱٬۲۳۴٬۵۶۷ ریال"""
	value = flt(value)
	text = f"{abs(value):,.0f}".replace(",", "٬")
	text = text.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
	return f"{'-' if value < 0 else ''}{text} {currency_label()}"


def number(value) -> str:
	value = flt(value)
	text = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
	return text.replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def jdate(value) -> str:
	return format_jalali(value) if value else ""


def require(doctype: str, ptype: str = "read"):
	if not frappe.has_permission(doctype, ptype):
		raise frappe.PermissionError


def list_url(doctype: str, filters: dict | None = None) -> str:
	"""A link to a list with filters already set; lists of values go as JSON, as Frappe reads them."""
	path = "/desk/" + frappe.scrub(doctype).replace("_", "-")
	if not filters:
		return path
	query = {
		k: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, list) else v
		for k, v in filters.items()
	}
	return f"{path}?{urlencode(query, quote_via=quote)}"


def report_url(report: str, filters: dict | None = None) -> str:
	path = "/desk/query-report/" + quote(report)
	return f"{path}?{urlencode(filters, quote_via=quote)}" if filters else path


def link(label: str, url: str) -> dict:
	return {"label": label, "url": url}


def doc_link(doctype: str, name: str) -> dict:
	return {"created": doctype, "name": name, "url": get_url_to_form(doctype, name)}


def table(headers: list[str], rows: list[list]) -> str:
	if not rows:
		return ""
	lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
	for row in rows:
		lines.append("| " + " | ".join(str(c if c is not None else "").replace("|", "/") for c in row) + " |")
	return "\n".join(lines)


def period_or(context, default="month") -> tuple[str, str, str]:
	"""(from, to, label) of the period named in the message, or this month / this year."""
	period = context.get("period")
	if period:
		return period["from"], period["to"], period["label"]
	if default == "year":
		jtoday = to_jalali(today())
		import jdatetime

		return str(jdatetime.date(jtoday.year, 1, 1).togregorian()), nowdate(), "امسال"
	jtoday = to_jalali(today())
	import jdatetime

	return str(jdatetime.date(jtoday.year, jtoday.month, 1).togregorian()), nowdate(), "این ماه"


def party_of(value: str) -> tuple[str, str]:
	""" "customer:X" -> ("Customer", "X")"""
	kind, _sep, name = (value or "").partition(":")
	return {
		"customer": "Customer",
		"supplier": "Supplier",
		"account": "Account",
		"cash_account": "Account",
	}.get(kind, kind), name


def party_label(doctype: str, name: str) -> str:
	field = {"Customer": "customer_name", "Supplier": "supplier_name"}.get(doctype)
	return (frappe.db.get_value(doctype, name, field) if field else None) or name


def count(doctype: str, filters) -> int:
	rows = frappe.get_list(doctype, filters=filters, fields=[{"COUNT": "name", "as": "n"}])
	return int(rows[0].n) if rows else 0


def total(doctype: str, filters, field: str) -> float:
	rows = frappe.get_list(doctype, filters=filters, fields=[{"SUM": field, "as": "total"}])
	return flt(rows[0].total) if rows else 0.0


def document_list(doctype, filters, columns, title, order_by="creation desc", limit=MAX_LINES, empty=None):
	"""A markdown table of documents, with a link to the whole filtered list.

	columns: (field, header, kind) with kind "money", "date", "status" or "" for plain text.
	"""
	require(doctype)
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=["name", *[c[0] for c in columns if c[0] != "name"]],
		order_by=order_by,
		limit=limit,
	)
	total_count = count(doctype, filters)
	url = list_url(doctype, filters)
	if not rows:
		return {"answer": empty or _("Nothing found."), "actions": [link(_("Open the list"), url)]}
	body = []
	for row in rows:
		cells = []
		for field, _header, kind in columns:
			value = row.get(field)
			if kind == "money":
				value = money(value)
			elif kind == "date":
				value = jdate(value)
			elif kind == "status":
				value = _(value or "")
			elif kind == "link":
				value = f"[{value}]({get_url_to_form(doctype, row.name)})"
			cells.append(value)
		body.append(cells)
	answer = f"**{title}** ({number(total_count)})\n\n" + table([c[1] for c in columns], body)
	if total_count > len(rows):
		answer += "\n\n" + _("Showing {0} of {1}.").format(number(len(rows)), number(total_count))
	return {"answer": answer, "actions": [link(_("Open the full list"), url)]}


def date_filter(field: str, start: str, end: str) -> list:
	return [field, "between", [start, end]]


def getdate_str(value) -> str:
	return str(getdate(value))
