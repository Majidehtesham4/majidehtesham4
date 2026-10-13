import frappe
from frappe import _
from frappe.utils import flt

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands.handlers import (
	company,
	doc_link,
	document_list,
	link,
	number,
	period_or,
	require,
	table,
)


def work_orders(context):
	return document_list(
		"Work Order",
		{"docstatus": 1, "company": company(), "status": ["in", ["Not Started", "In Process"]]},
		[
			("name", _("Work Order"), "link"),
			("item_name", _("Item"), ""),
			("qty", _("Quantity"), ""),
			("produced_qty", _("Produced"), ""),
			("status", _("Status"), "status"),
		],
		_("Open work orders"),
		empty=_("No open work orders."),
	)


def _bom(item):
	return frappe.db.get_value(
		"BOM", {"item": item, "is_default": 1, "is_active": 1, "docstatus": 1}
	) or frappe.db.get_value("BOM", {"item": item, "is_active": 1, "docstatus": 1})


def create_work_order(context):
	require("Work Order", "create")
	item = context.get("item")
	bom = _bom(item)
	item_name = frappe.db.get_value("Item", item, "item_name")
	if not bom:
		return _("{0} has no bill of materials, so it cannot be produced yet. Define its BOM first.").format(
			item_name
		)
	from erpnext.manufacturing.doctype.work_order.work_order import get_default_warehouse

	the_company = company()
	doc = frappe.get_doc(
		{
			"doctype": "Work Order",
			"company": the_company,
			"production_item": item,
			"bom_no": bom,
			"qty": flt(context.get("qty")),
			**{k: v for k, v in get_default_warehouse(the_company).items() if v},
		}
	)
	doc.get_items_and_operations_from_bom()
	doc.insert()
	return {
		"answer": _("Draft work order: {0} × {1}.").format(item_name, number(doc.qty)),
		"actions": [doc_link("Work Order", doc.name)],
	}


def bom_info(context):
	require("BOM")
	item = context.get("item")
	bom = _bom(item)
	item_name = frappe.db.get_value("Item", item, "item_name")
	if not bom:
		return _("{0} has no bill of materials.").format(item_name)
	doc = frappe.get_doc("BOM", bom)
	answer = (
		_("Materials for {0} {1}:").format(number(doc.quantity), item_name)
		+ "\n\n"
		+ table(
			[_("Item"), _("Quantity"), _("Unit")], [[r.item_name, number(r.qty), _(r.uom)] for r in doc.items]
		)
	)
	return {"answer": answer, "actions": [link(_("Open"), get_url_to_form("BOM", bom))]}


def production_total(context):
	require("Stock Entry")
	start, end, label = period_or(context)
	rows = frappe.db.sql(
		"""select detail.item_code, detail.item_name, sum(detail.transfer_qty) qty
		from `tabStock Entry Detail` detail join `tabStock Entry` entry on entry.name = detail.parent
		where entry.docstatus=1 and entry.purpose='Manufacture' and entry.company=%s and detail.is_finished_item=1
			and entry.posting_date between %s and %s
		group by detail.item_code, detail.item_name order by qty desc""",
		(company(), start, end),
		as_dict=True,
	)
	if not rows:
		return _("Nothing was produced in {0}.").format(label)
	return f"**{_('Production')}** ({label})\n\n" + table(
		[_("Item"), _("Quantity")], [[r.item_name, number(r.qty)] for r in rows]
	)
