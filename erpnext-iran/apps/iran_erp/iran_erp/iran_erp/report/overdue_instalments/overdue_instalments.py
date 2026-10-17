"""Instalments past their date and not paid: whose, how late, the cheque and the late fee so far."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(filters.date or nowdate())
	conditions, values = "", {"today": today}
	for key in ("company", "branch", "customer"):
		if filters.get(key):
			conditions += f" and s.{key} = %({key})s"
			values[key] = filters.get(key)
	rows = frappe.db.sql(
		f"""select s.name as contract, s.customer, s.customer_name, s.description, s.late_fee_rate,
			i.idx as instalment, i.due_date, i.amount, i.cheque, c.cheque_number, c.status as cheque_status
		from `tabIran Instalment` i
		join `tabIran Instalment Sale` s on s.name = i.parent
		left join `tabIran Cheque` c on c.name = i.cheque
		where s.docstatus = 1 and i.status in ('Unpaid', 'Overdue') and i.due_date < %(today)s {conditions}
		order by i.due_date asc""",
		values,
		as_dict=True,
	)
	for row in rows:
		row.days = date_diff(today, row.due_date)
		row.late_fee = flt(flt(row.amount) * flt(row.late_fee_rate) / 100 / 30 * row.days, 0)
		row.cheque_status = _(row.cheque_status) if row.cheque_status else ""
	columns = [
		{
			"fieldname": "contract",
			"label": _("Contract"),
			"fieldtype": "Link",
			"options": "Iran Instalment Sale",
			"width": 150,
		},
		{"fieldname": "customer_name", "label": _("Customer"), "fieldtype": "Data", "width": 170},
		{"fieldname": "description", "label": _("What Is Sold"), "fieldtype": "Data", "width": 180},
		{"fieldname": "instalment", "label": _("Instalment"), "fieldtype": "Int", "width": 80},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "days", "label": _("Days Late"), "fieldtype": "Int", "width": 90},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "cheque_number", "label": _("Cheque Number"), "fieldtype": "Data", "width": 120},
		{"fieldname": "cheque_status", "label": _("Cheque Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "late_fee", "label": _("Late Fee to Date"), "fieldtype": "Currency", "width": 140},
	]
	return columns, rows
