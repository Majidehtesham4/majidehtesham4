"""What is waiting for the current user: approvals, drafts to submit, assigned tasks and due items.

Every count goes through Frappe's permission checks, so each user only sees their own work.
"""

import frappe
from frappe import _
from frappe.utils import add_days, nowdate

# Documents whose drafts usually wait for someone to review and submit them
DRAFT_DOCTYPES = (
	"Sales Invoice",
	"Purchase Invoice",
	"Payment Entry",
	"Journal Entry",
	"Stock Entry",
	"Sales Order",
	"Purchase Order",
	"Quotation",
	"Delivery Note",
	"Purchase Receipt",
	"Material Request",
	"Iran Cheque",
)
CHEQUE_DUE_DAYS = 7


def _count(doctype: str, filters: dict) -> int:
	rows = frappe.get_list(doctype, filters=filters, fields=[{"COUNT": "name", "as": "count"}])
	return int(rows[0].count) if rows else 0


def _item(section: str, label: str, doctype: str, filters: dict, count: int) -> dict:
	return {"section": section, "label": label, "doctype": doctype, "filters": filters, "count": count}


@frappe.whitelist()
def get_inbox() -> dict:
	user = frappe.session.user
	items = []

	# Workflow approvals: the Workflow Action list is already limited to the user's roles
	if frappe.has_permission("Workflow Action", "read"):
		rows = frappe.get_list(
			"Workflow Action",
			filters={"status": "Open"},
			fields=["reference_doctype", {"COUNT": "name", "as": "count"}],
			group_by="reference_doctype",
		)
		for row in rows:
			items.append(
				_item(
					"approvals",
					_("{0} awaiting your approval").format(_(row.reference_doctype)),
					"Workflow Action",
					{"status": "Open", "reference_doctype": row.reference_doctype},
					int(row.count),
				)
			)

	for doctype in DRAFT_DOCTYPES:
		if frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "submit"):
			count = _count(doctype, {"docstatus": 0})
			if count:
				items.append(
					_item(
						"drafts",
						_("{0} awaiting submission").format(_(doctype)),
						doctype,
						{"docstatus": 0},
						count,
					)
				)

	todo_filters = {"allocated_to": user, "status": "Open"}
	count = _count("ToDo", todo_filters)
	if count:
		items.append(_item("tasks", _("Tasks assigned to you"), "ToDo", todo_filters, count))

	if frappe.has_permission("Iran Cheque", "read"):
		cheque_filters = {
			"docstatus": 1,
			"status": ["in", ["In Hand", "Deposited", "Issued"]],
			"due_date": ["<=", add_days(nowdate(), CHEQUE_DUE_DAYS)],
		}
		count = _count("Iran Cheque", cheque_filters)
		if count:
			items.append(
				_item(
					"alerts",
					_("Cheques due within {0} days").format(CHEQUE_DUE_DAYS),
					"Iran Cheque",
					cheque_filters,
					count,
				)
			)

	for doctype, label in (
		("Sales Invoice", _("Overdue sales invoices")),
		("Purchase Invoice", _("Overdue purchase invoices")),
	):
		if frappe.has_permission(doctype, "read"):
			filters = {"docstatus": 1, "status": "Overdue"}
			count = _count(doctype, filters)
			if count:
				items.append(_item("alerts", label, doctype, filters, count))

	return {"items": items, "total": sum(item["count"] for item in items)}
