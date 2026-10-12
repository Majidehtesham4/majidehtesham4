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

from iran_erp.ai.bank import match_bank_statement
from iran_erp.ai.files import get_file, parse_date, read_table
from iran_erp.utils.jalali import format_jalali
from iran_erp.utils.national_id import normalize_digits

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


def read_table_file(file_url: str, max_rows: int = 15):
	"""The first rows of an attached CSV or Excel file, to see its columns."""
	rows = read_table(get_file(file_url))
	return {
		"total_rows": len(rows),
		"first_rows": _value([[_cell(c) for c in row] for row in rows[: min(int(max_rows or 15), 50)]]),
	}


def _cell(value):
	if isinstance(value, float) and value.is_integer():
		return int(value)
	return value


def find_party(
	doctype: str, name: str | None = None, economic_code: str | None = None, national_id: str | None = None
):
	"""A customer or supplier by economic code, national ID or name."""
	meta = frappe.get_meta(doctype)
	for field, value in (
		("iran_economic_code", economic_code),
		("iran_national_id", national_id),
		("tax_id", economic_code),
	):
		value = normalize_digits(value or "").strip()
		if value and meta.has_field(field):
			found = frappe.get_list(doctype, filters={field: value}, pluck="name", limit=1)
			if found:
				return found[0]
	if name:
		name_field = "supplier_name" if doctype == "Supplier" else "customer_name"
		found = frappe.get_list(
			doctype, filters={name_field: ["like", f"%{name.strip()}%"]}, pluck="name", limit=2
		)
		if len(found) == 1:
			return found[0]
	return None


def create_purchase_invoice_draft(
	items: list,
	supplier: str | None = None,
	supplier_name: str | None = None,
	supplier_economic_code: str | None = None,
	supplier_national_id: str | None = None,
	bill_no: str | None = None,
	bill_date: str | None = None,
	company: str | None = None,
	apply_vat: bool = False,
	invoice_total: float | None = None,
	file_url: str | None = None,
):
	"""A draft purchase invoice from what was read off a supplier's invoice."""
	_check_writable("Purchase Invoice")
	if not (supplier and frappe.db.exists("Supplier", supplier)):
		supplier = find_party(
			"Supplier", supplier_name or supplier, supplier_economic_code, supplier_national_id
		)
	if not supplier:
		return {
			"error": "Supplier not found. Ask the user which supplier this is, or whether to create it "
			"(create_draft_document with doctype Supplier), then call this tool again with supplier."
		}
	company = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	expense_account = frappe.get_cached_value("Company", company, "default_expense_account")
	rows = []
	for item in items or []:
		row = {
			"qty": item.get("qty") or 1,
			"rate": item.get("rate") or 0,
			"discount_amount": item.get("discount_amount") or 0,
		}
		item_code = item.get("item_code")
		if item_code and frappe.db.exists("Item", item_code):
			row["item_code"] = item_code
		else:
			# Lines that are not items in the system are booked to an expense account
			description = item.get("description") or item.get("item_name") or _("Item")
			row.update(
				{
					"item_name": description[:140],
					"description": description,
					"uom": item.get("uom") if frappe.db.exists("UOM", item.get("uom") or "") else "Nos",
					"expense_account": item.get("expense_account") or expense_account,
				}
			)
		rows.append(row)
	if not rows:
		frappe.throw(_("The invoice has no items"))

	doc = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": company,
			"supplier": supplier,
			"bill_no": bill_no,
			"bill_date": parse_date(bill_date) if bill_date else None,
			"items": rows,
		}
	)
	if apply_vat:
		template = frappe.db.get_value(
			"Purchase Taxes and Charges Template", {"company": company, "is_default": 1, "disabled": 0}
		)
		if template:
			doc.taxes_and_charges = template
			doc.append_taxes_from_master()
	doc.docstatus = 0
	doc.insert()
	if file_url:
		attach_file_to_document(file_url, "Purchase Invoice", doc.name)
	result = {
		"created": "Purchase Invoice",
		"name": doc.name,
		"url": get_url_to_form("Purchase Invoice", doc.name),
		"supplier": supplier,
		"net_total": doc.net_total,
		"taxes": doc.total_taxes_and_charges,
		"grand_total": doc.grand_total,
	}
	if invoice_total is not None and abs(float(invoice_total) - doc.grand_total) >= 1:
		result["warning"] = (
			f"The draft totals {doc.grand_total:,.0f} but the document says {float(invoice_total):,.0f}; "
			"tell the user to check the lines and taxes."
		)
	return result


def attach_file_to_document(file_url: str, doctype: str, name: str):
	"""Attach an uploaded file to a document so it is kept with it."""
	source = get_file(file_url)
	frappe.get_doc(doctype, name).check_permission("write")
	attached = frappe.get_doc(
		{
			"doctype": "File",
			"file_url": source.file_url,
			"file_name": source.file_name,
			"is_private": source.is_private,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
		}
	).insert()
	return {"attached": attached.file_name, "to": f"{doctype} {name}"}


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
	"read_table_file": read_table_file,
	"match_bank_statement": match_bank_statement,
	"create_purchase_invoice_draft": create_purchase_invoice_draft,
	"attach_file_to_document": attach_file_to_document,
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
	_fn(
		"read_table_file",
		"Read the first rows of an attached CSV or XLSX file (such as a bank statement) to see its "
		"header row and columns.",
		{"file_url": {"type": "string"}, "max_rows": {"type": "integer"}},
		["file_url"],
	),
	_fn(
		"match_bank_statement",
		"Reconcile an attached bank statement (CSV/XLSX) with the ledger of a bank account. Map the "
		"statement's column names (exactly as in the header row): the date column, and either one signed "
		"amount column or separate deposit and withdrawal columns. Jalali or Gregorian dates and Persian "
		"digits are understood. Returns matched counts, statement lines with no ledger entry (often bank "
		"fees, interest or unrecorded receipts), ledger entries missing from the statement (often cheques "
		"not yet cleared), and both closing balances.",
		{
			"file_url": {"type": "string"},
			"bank_account": {
				"type": "string",
				"description": "Account name of the bank in the chart of accounts",
			},
			"date_column": {"type": "string"},
			"deposit_column": {"type": "string"},
			"withdrawal_column": {"type": "string"},
			"amount_column": {"type": "string", "description": "Signed amount; positive is money in"},
			"description_column": {"type": "string"},
			"reference_column": {"type": "string", "description": "Cheque or tracking number column"},
			"balance_column": {"type": "string"},
			"header_row": {"type": "integer", "description": "1-based row number of the header row"},
			"tolerance_days": {"type": "integer", "description": "Allowed date difference, default 3"},
		},
		["file_url", "bank_account", "date_column"],
	),
	_fn(
		"create_purchase_invoice_draft",
		"Create a draft purchase invoice from a supplier invoice the user attached (image or PDF). Read "
		"the supplier (name, economic code, national ID), invoice number and date, and every line "
		"(description, quantity, unit price, discount). Use item_code only for items found in the "
		"system; other lines are booked to the default expense account. Set apply_vat when the invoice "
		"charges VAT, and pass the invoice's grand total so differences are reported. Pass the file_url "
		"so the file is attached to the draft.",
		{
			"supplier": {"type": "string", "description": "Supplier record name, when known"},
			"supplier_name": {"type": "string"},
			"supplier_economic_code": {"type": "string"},
			"supplier_national_id": {"type": "string"},
			"bill_no": {"type": "string"},
			"bill_date": {"type": "string", "description": "As printed, e.g. 1405/07/18"},
			"items": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"item_code": {"type": "string"},
						"description": {"type": "string"},
						"qty": {"type": "number"},
						"uom": {"type": "string"},
						"rate": {"type": "number", "description": "Unit price in rial"},
						"discount_amount": {"type": "number", "description": "Discount per unit"},
					},
				},
			},
			"apply_vat": {"type": "boolean"},
			"invoice_total": {"type": "number"},
			"company": {"type": "string"},
			"file_url": {"type": "string"},
		},
		["items"],
	),
	_fn(
		"attach_file_to_document",
		"Attach a file the user uploaded to a document, e.g. a receipt to a journal entry.",
		{"file_url": {"type": "string"}, "doctype": {"type": "string"}, "name": {"type": "string"}},
		["file_url", "doctype", "name"],
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
