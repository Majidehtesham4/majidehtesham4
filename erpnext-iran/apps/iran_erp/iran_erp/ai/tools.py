"""Tools the AI assistant can call.

Every tool runs as the user who asked the question, so Frappe's normal permission
checks decide what they can read or create. The assistant can only create drafts:
nothing here submits, cancels or deletes a document.
"""

import datetime
import json
import re

import frappe
from frappe import _
from frappe.utils import get_url_to_form
from frappe.utils.html_utils import sanitize_html
from frappe.utils.xlsxutils import make_xlsx

from iran_erp.utils.jalali import format_jalali

MAX_ROWS = 200
MAX_TEXT = 2000
# Configuration areas the assistant must not create or change records in
BLOCKED_MODULES = {"Core", "Custom", "Desk", "Email", "Integrations", "Automation", "Website Theme"}
AGGREGATE = re.compile(r"^\s*(sum|count|avg|min|max)\(\s*(\*|[\w.`]+)\s*\)(?:\s+as\s+(\w+))?\s*$", re.I)
LAYOUT_FIELDTYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}


def _value(value):
	"""Make a value JSON friendly; dates get their Jalali form alongside."""
	if isinstance(value, datetime.datetime):
		return f"{value:%Y-%m-%d %H:%M} ({format_jalali(value.date())})"
	if isinstance(value, datetime.date):
		return f"{value:%Y-%m-%d} ({format_jalali(value)})"
	if isinstance(value, datetime.timedelta):
		return str(value)
	if isinstance(value, str) and len(value) > MAX_TEXT:
		return value[:MAX_TEXT] + "…"
	if isinstance(value, list):
		return [_value(v) for v in value[:50]]
	if isinstance(value, dict):
		return {k: _value(v) for k, v in value.items()}
	return value


def _check_writable(doctype: str):
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle or meta.module in BLOCKED_MODULES:
		frappe.throw(_("The assistant is not allowed to create or change {0} records.").format(_(doctype)))


def get_company_info(company: str | None = None):
	company = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	if not company:
		return {"error": "No company is set up yet."}
	doc = frappe.get_doc("Company", company)
	doc.check_permission("read")
	info = {
		field: doc.get(field)
		for field in (
			"company_name",
			"abbr",
			"country",
			"default_currency",
			"date_of_establishment",
			"phone_no",
			"email",
			"website",
			"tax_id",
			"iran_national_id",
			"iran_economic_code",
			"company_description",
		)
		if doc.get(field)
	}
	addresses = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		pluck="parent",
	)
	if addresses:
		from frappe.contacts.doctype.address.address import get_address_display

		info["address"] = get_address_display(addresses[0])
	return _value(info)


def describe_doctype(doctype: str):
	meta = frappe.get_meta(doctype)
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No permission to read {0}").format(_(doctype)))
	fields = [
		{
			"fieldname": df.fieldname,
			"label": _(df.label) if df.label else None,
			"fieldtype": df.fieldtype,
			"options": df.options,
			"required": bool(df.reqd),
		}
		for df in meta.fields
		if df.fieldtype not in LAYOUT_FIELDTYPES
	]
	return {"doctype": doctype, "is_submittable": bool(meta.is_submittable), "fields": fields[:150]}


def _field(field):
	"""Frappe v16 only takes aggregates as dicts; accept the usual "sum(x) as y" form too."""
	match = AGGREGATE.match(field) if isinstance(field, str) else None
	if not match:
		return field
	function, column, alias = match.groups()
	return {function.upper(): column.strip("`"), "as": alias or function.lower()}


def search_documents(
	doctype: str,
	filters=None,
	fields: list | None = None,
	order_by: str | None = None,
	group_by: str | None = None,
	limit: int = 20,
):
	rows = frappe.get_list(
		doctype,
		filters=filters or {},
		fields=[_field(f) for f in (fields or ["name"])],
		order_by=order_by,
		group_by=group_by,
		limit_page_length=min(int(limit or 20), MAX_ROWS),
	)
	return {"count": len(rows), "rows": _value(rows)}


def get_document(doctype: str, name: str):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	data = doc.as_dict(no_default_fields=True, no_child_table_fields=True)
	data["url"] = get_url_to_form(doctype, name)
	return _value(data)


def run_report(report_name: str, filters: dict | None = None, limit: int = 100):
	from frappe.desk.query_report import run

	result = run(report_name, filters=frappe._dict(filters or {}), ignore_prepared_report=True)
	columns = []
	for col in result.get("columns") or []:
		if isinstance(col, dict):
			columns.append({"fieldname": col.get("fieldname"), "label": _(col.get("label") or "")})
		else:
			columns.append({"fieldname": str(col), "label": str(col)})
	rows = result.get("result") or []
	return {
		"columns": columns,
		"row_count": len(rows),
		"rows": _value(rows[: min(int(limit or 100), MAX_ROWS)]),
		"message": result.get("message"),
	}


def create_draft_document(doctype: str, data: dict):
	_check_writable(doctype)
	data = {k: v for k, v in (data or {}).items() if k not in ("doctype", "name", "docstatus", "owner")}
	doc = frappe.get_doc({"doctype": doctype, **data})
	doc.docstatus = 0
	doc.insert()
	return {"created": doctype, "name": doc.name, "url": get_url_to_form(doctype, doc.name)}


def update_draft_document(doctype: str, name: str, changes: dict):
	_check_writable(doctype)
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 0:
		frappe.throw(_("Only draft documents can be changed by the assistant."))
	changes = {k: v for k, v in (changes or {}).items() if k not in ("doctype", "name", "docstatus", "owner")}
	if doctype == "Web Page" and changes.get("main_section_html"):
		changes["main_section_html"] = sanitize_html(changes["main_section_html"], always_sanitize=True)
	doc.update(changes)
	doc.save()
	return {"updated": doctype, "name": doc.name, "url": get_url_to_form(doctype, doc.name)}


def create_web_page(title: str, route: str, html: str, publish: bool = False):
	doc = frappe.get_doc(
		{
			"doctype": "Web Page",
			"title": title,
			"route": route,
			"content_type": "HTML",
			# Model output becomes a public page, so strip scripts and unsafe attributes
			"main_section_html": sanitize_html(
				f'<div dir="rtl" class="iran-ai-page">{html}</div>', always_sanitize=True
			),
			"published": 1 if publish else 0,
		}
	)
	doc.insert()
	return {
		"created": "Web Page",
		"name": doc.name,
		"url": get_url_to_form("Web Page", doc.name),
		"public_url": frappe.utils.get_url(doc.route),
		"published": bool(doc.published),
	}


def export_excel(title: str, columns: list, rows: list):
	data = [list(columns)] + [list(r) for r in rows]
	xlsx = make_xlsx(data, (title or "Sheet")[:30]).getvalue()
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{frappe.scrub(title or 'export')}.xlsx",
			"content": xlsx,
			"is_private": 1,
		}
	)
	file.save()
	return {"file_url": file.file_url, "file_name": file.file_name}


TOOLS = {
	"get_company_info": get_company_info,
	"describe_doctype": describe_doctype,
	"search_documents": search_documents,
	"get_document": get_document,
	"run_report": run_report,
	"create_draft_document": create_draft_document,
	"update_draft_document": update_draft_document,
	"create_web_page": create_web_page,
	"export_excel": export_excel,
}


def _fn(name, description, properties, required=()):
	return {
		"type": "function",
		"function": {
			"name": name,
			"description": description,
			"parameters": {"type": "object", "properties": properties, "required": list(required)},
		},
	}


TOOL_SCHEMAS = [
	_fn(
		"get_company_info",
		"Company details from the system settings: name, address, phone, email, website, national ID, "
		"economic code, currency. Use it for anything about the company instead of guessing.",
		{"company": {"type": "string", "description": "Company name; omit for the default company"}},
	),
	_fn(
		"describe_doctype",
		"List the fields of a document type (DocType), with their labels and types. Call it before "
		"filtering or creating a document type whose field names you are not sure about.",
		{"doctype": {"type": "string", "description": "e.g. Sales Invoice, Customer, Item"}},
		["doctype"],
	),
	_fn(
		"search_documents",
		"Search records of a DocType with Frappe filters. Supports aggregates in fields such as "
		"'sum(grand_total) as total' or 'count(*) as invoices' together with group_by. Use this for "
		"lists, counts and totals. Only submitted documents have docstatus 1; drafts are 0.",
		{
			"doctype": {"type": "string"},
			"filters": {
				"description": "Frappe filters, e.g. {'docstatus': 1, 'posting_date': ['between', "
				"['2026-03-21', '2026-04-20']]} or a list of [field, operator, value]",
			},
			"fields": {"type": "array", "items": {"type": "string"}},
			"order_by": {"type": "string", "description": "e.g. 'posting_date desc'"},
			"group_by": {"type": "string"},
			"limit": {"type": "integer", "description": "Max rows, up to 200"},
		},
		["doctype"],
	),
	_fn(
		"get_document",
		"Read one full document, including its child tables.",
		{"doctype": {"type": "string"}, "name": {"type": "string"}},
		["doctype", "name"],
	),
	_fn(
		"run_report",
		"Run a standard report such as 'General Ledger', 'Trial Balance', 'Profit and Loss Statement', "
		"'Balance Sheet', 'Accounts Receivable', 'Accounts Payable' or 'Stock Balance'. Reports need "
		"their usual filters, e.g. company, from_date, to_date, period_start_date, period_end_date.",
		{
			"report_name": {"type": "string"},
			"filters": {"type": "object"},
			"limit": {"type": "integer"},
		},
		["report_name"],
	),
	_fn(
		"create_draft_document",
		"Create a new document as a draft (never submitted). Child tables are lists of row objects, "
		"e.g. {'customer': 'X', 'items': [{'item_code': 'Y', 'qty': 2}]}.",
		{"doctype": {"type": "string"}, "data": {"type": "object"}},
		["doctype", "data"],
	),
	_fn(
		"update_draft_document",
		"Change fields of an existing draft document (including Web Pages).",
		{"doctype": {"type": "string"}, "name": {"type": "string"}, "changes": {"type": "object"}},
		["doctype", "name", "changes"],
	),
	_fn(
		"create_web_page",
		"Create a website page from HTML. It stays unpublished unless the user explicitly asked to "
		"publish it. Write right-to-left Persian content with simple semantic HTML (sections, h2, p, "
		"ul, a) and inline styles; no scripts.",
		{
			"title": {"type": "string"},
			"route": {"type": "string", "description": "URL path in latin letters, e.g. 'services'"},
			"html": {"type": "string"},
			"publish": {"type": "boolean"},
		},
		["title", "route", "html"],
	),
	_fn(
		"export_excel",
		"Save a table as an Excel file the user can download.",
		{
			"title": {"type": "string"},
			"columns": {"type": "array", "items": {"type": "string"}},
			"rows": {"type": "array", "items": {"type": "array", "items": {}}},
		},
		["title", "columns", "rows"],
	),
]


def execute_tool(name: str, arguments: str | dict):
	"""Run a tool call and return (result, action) where action describes anything created."""
	if name not in TOOLS:
		return {"error": f"Unknown tool {name}"}, None
	try:
		args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
	except ValueError:
		return {"error": "Arguments are not valid JSON"}, None

	savepoint = "iran_ai_tool"
	frappe.db.savepoint(savepoint)
	try:
		result = TOOLS[name](**args)
	except Exception as e:
		frappe.db.rollback(save_point=savepoint)
		frappe.clear_last_message()
		message = frappe.utils.strip_html(str(e)) or e.__class__.__name__
		return {"error": message}, None

	action = None
	if isinstance(result, dict) and (
		result.get("created") or result.get("updated") or result.get("file_url")
	):
		action = {"tool": name, **{k: v for k, v in result.items() if k != "rows"}}
	return result, action
