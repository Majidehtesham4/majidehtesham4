"""The cars in the lot: where each one is, whose it is, how long it has stood, what it cost and
what it is offered for."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"status": ("not in", ("Sold", "Exited"))}
	for key in ("branch", "parking", "ownership", "status", "car_model"):
		if filters.get(key):
			conditions[key] = filters.get(key)
	today = getdate(nowdate())
	rows = frappe.get_all(
		"Iran Vehicle",
		filters=conditions,
		fields=[
			"name",
			"title",
			"car_model",
			"year",
			"color",
			"plate",
			"status",
			"branch",
			"parking",
			"parking_spot",
			"ownership",
			"entry_date",
			"total_cost",
			"asking_price",
			"body_summary",
		],
		order_by="entry_date asc",
	)
	for row in rows:
		row.days = date_diff(today, row.entry_date) if row.entry_date else 0
		row.status = _(row.status)
		row.ownership_label = _(row.ownership)
		row.margin = flt(row.asking_price) - flt(row.total_cost) if row.ownership == "Business" else None
	columns = [
		{
			"fieldname": "name",
			"label": _("Code"),
			# Data, not Link: a link shows the car's title, and the title is the next column
			"fieldtype": "Data",
			"width": 110,
		},
		{"fieldname": "title", "label": _("Car"), "fieldtype": "Data", "width": 230},
		{"fieldname": "status", "label": _("Status in the Lot"), "fieldtype": "Data", "width": 120},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch", "width": 120},
		{
			"fieldname": "parking",
			"label": _("Parking"),
			"fieldtype": "Link",
			"options": "Iran Parking",
			"width": 120,
		},
		{"fieldname": "parking_spot", "label": _("Spot Number"), "fieldtype": "Data", "width": 80},
		{"fieldname": "ownership_label", "label": _("Owned By"), "fieldtype": "Data", "width": 100},
		{"fieldname": "days", "label": _("Days in the Lot"), "fieldtype": "Int", "width": 90},
		{"fieldname": "total_cost", "label": _("Total Cost"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "asking_price", "label": _("Asking Price"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "margin", "label": _("Expected Margin"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "body_summary", "label": _("Body Summary"), "fieldtype": "Data", "width": 260},
	]
	statuses = {}
	for row in rows:
		statuses[row.status] = statuses.get(row.status, 0) + 1
	chart = {
		"data": {
			"labels": list(statuses),
			"datasets": [{"name": _("Cars"), "values": list(statuses.values())}],
		},
		"type": "donut",
	}
	return columns, rows, None, chart
