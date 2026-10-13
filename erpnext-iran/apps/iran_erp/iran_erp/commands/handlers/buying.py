import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

from iran_erp.ai import tools
from iran_erp.commands import entities
from iran_erp.commands.engine import NeedSlot
from iran_erp.commands.handlers import (
	company,
	doc_link,
	document_list,
	link,
	list_url,
	money,
	number,
	party_label,
	require,
)
from iran_erp.commands.handlers.selling import BUYING_PRICE_LIST, _invoice_filters, _summary, _top, _totals


def _lines(context):
	lines = (context.get("items") or {}).get("lines") or []
	result = []
	for line in lines:
		rate = flt(line.get("rate"))
		if not rate:
			rate = flt(
				frappe.db.get_value(
					"Item Price",
					{"item_code": line["item"], "price_list": BUYING_PRICE_LIST},
					"price_list_rate",
				)
			) or flt(frappe.db.get_value("Item", line["item"], "last_purchase_rate"))
		result.append({"item_code": line["item"], "qty": flt(line.get("qty")) or 1, "rate": rate})
	return result


def purchases_total(context):
	require("Purchase Invoice")
	filters, label = _invoice_filters(context, party_field="supplier")
	row = _totals("Purchase Invoice", filters)
	who = f" {_('from')} {party_label('Supplier', filters['supplier'])}" if filters.get("supplier") else ""
	if not row.n:
		return _("No purchases{0} in {1}.").format(who, label)
	answer = _("Purchases{0} in {1}: {2} invoices, {3} before tax, {4} with tax.").format(
		who, label, number(row.n), money(row.net), money(row.gross)
	)
	return {
		"answer": answer,
		"actions": [link(_("Open the invoices"), list_url("Purchase Invoice", filters))],
	}


def top_suppliers(context):
	return _top("Purchase Invoice", "supplier", "supplier_name", context, _("Top suppliers"))


def last_purchase_invoices(context):
	filters = {"company": company(), "docstatus": ["<", 2]}
	if context.get("supplier"):
		filters["supplier"] = context.get("supplier")
	if context.get("period"):
		filters["posting_date"] = ["between", [context.get("period")["from"], context.get("period")["to"]]]
	return document_list(
		"Purchase Invoice",
		filters,
		[
			("name", _("Invoice"), "link"),
			("supplier_name", _("Supplier"), ""),
			("posting_date", _("Date"), "date"),
			("grand_total", _("Total"), "money"),
			("status", _("Status"), "status"),
		],
		_("Latest purchase invoices"),
		limit=context.get("limit", 10),
	)


def create_purchase_invoice(context):
	result = tools.create_purchase_invoice_draft(
		items=_lines(context),
		supplier=context.get("supplier"),
		apply_vat=context.get("vat") == "yes",
		company=company(),
	)
	if result.get("error"):
		frappe.throw(result["error"])
	doc = frappe.get_doc("Purchase Invoice", result["name"])
	return {
		"answer": _("Draft purchase invoice from {0}:").format(doc.supplier_name) + "\n\n" + _summary(doc),
		"actions": [doc_link("Purchase Invoice", doc.name)],
	}


def create_purchase_order(context):
	require("Purchase Order", "create")
	supplier = context.get("supplier")
	schedule = context.get("date") or add_days(nowdate(), 7)
	doc = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"company": company(),
			"supplier": supplier,
			"transaction_date": nowdate(),
			"schedule_date": schedule,
			"items": [{**line, "schedule_date": schedule} for line in _lines(context)],
		}
	)
	doc.insert()
	return {
		"answer": _("Draft purchase order to {0}:").format(party_label("Supplier", supplier))
		+ "\n\n"
		+ _summary(doc),
		"actions": [doc_link("Purchase Order", doc.name)],
	}


def pending_purchase_orders(context):
	filters = {
		"docstatus": 1,
		"company": company(),
		"status": ["in", ["To Receive and Bill", "To Receive", "To Bill"]],
	}
	if context.get("supplier"):
		filters["supplier"] = context.get("supplier")
	return document_list(
		"Purchase Order",
		filters,
		[
			("name", _("Order"), "link"),
			("supplier_name", _("Supplier"), ""),
			("schedule_date", _("Required By"), "date"),
			("grand_total", _("Total"), "money"),
			("status", _("Status"), "status"),
		],
		_("Open purchase orders"),
		order_by="schedule_date asc",
		empty=_("Every purchase order is received and billed."),
	)


def create_supplier(context):
	require("Supplier", "create")
	name = context.get("name")
	mobile = context.get("mobile")
	existing = tools.find_party("Supplier", name)
	if existing and frappe.db.get_value("Supplier", existing, "supplier_name") == name:
		return _("{0} is already a supplier.").format(name)
	group = frappe.db.get_value("Supplier Group", {"is_group": 0}) or "All Supplier Groups"
	doc = frappe.get_doc(
		{"doctype": "Supplier", "supplier_name": name, "supplier_group": group, "mobile_no": mobile}
	).insert()
	if mobile:
		frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": name,
				"phone_nos": [{"phone": mobile, "is_primary_mobile_no": 1}],
				"links": [{"link_doctype": "Supplier", "link_name": doc.name}],
			}
		).insert()
	entities.forget("supplier")
	return {
		"answer": _("Supplier {0} was created.").format(name),
		"actions": [doc_link("Supplier", doc.name)],
	}


def material_requests(context):
	return document_list(
		"Material Request",
		{
			"docstatus": 1,
			"company": company(),
			"status": ["in", ["Pending", "Partially Ordered", "Partially Received"]],
		},
		[
			("name", _("Request"), "link"),
			("material_request_type", _("Type"), "status"),
			("schedule_date", _("Required By"), "date"),
			("status", _("Status"), "status"),
		],
		_("Open material requests"),
		order_by="schedule_date asc",
		empty=_("No open material requests."),
	)


def create_material_request(context):
	require("Material Request", "create")
	schedule = context.get("date") or add_days(nowdate(), 7)
	lines = [
		{"item_code": line["item_code"], "qty": line["qty"], "schedule_date": schedule}
		for line in _lines(context)
	]
	if not lines:
		raise NeedSlot("items", _("Which items, and how many?"))
	doc = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": company(),
			"transaction_date": nowdate(),
			"schedule_date": schedule,
			"items": lines,
		}
	).insert()
	rows = "\n".join(f"- {r.item_name}: {number(r.qty)}" for r in doc.items)
	return {
		"answer": _("Draft material request:") + "\n" + rows,
		"actions": [doc_link("Material Request", doc.name)],
	}
