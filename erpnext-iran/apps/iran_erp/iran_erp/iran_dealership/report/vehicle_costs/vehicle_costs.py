"""What preparation, repairs and paperwork cost: per service, or per car, in a period. The services
come from one list, so the same work is counted together for every car."""

import frappe
from frappe import _
from frappe.utils import add_months, flt, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	values = {
		"from_date": filters.from_date or add_months(nowdate(), -1),
		"to_date": filters.to_date or nowdate(),
	}
	conditions = "c.status = 'Done' and c.date between %(from_date)s and %(to_date)s"
	for key, column in (("branch", "v.branch"), ("category", "c.category"), ("service", "c.service")):
		if filters.get(key):
			conditions += f" and {column} = %({key})s"
			values[key] = filters.get(key)
	by_car = filters.group_by == "Car"
	group = "v.name" if by_car else "c.service"
	rows = frappe.db.sql(
		f"""select {group} as name, max(v.title) as title, max(c.category) as category,
			count(*) as times, sum(c.amount) as amount,
			sum(case when c.done_by = 'Own Workshop' then c.amount else 0 end) as own_workshop
		from `tabIran Vehicle Cost` c join `tabIran Vehicle` v on v.name = c.parent
		where {conditions} group by {group} order by amount desc""",
		values,
		as_dict=True,
	)
	for row in rows:
		row.category = _(row.category) if row.category else ""
		row.outside = flt(row.amount) - flt(row.own_workshop)
	first = (
		{"fieldname": "name", "label": _("Car"), "fieldtype": "Link", "options": "Iran Vehicle", "width": 110}
		if by_car
		else {
			"fieldname": "name",
			"label": _("Service"),
			"fieldtype": "Link",
			"options": "Iran Vehicle Service",
			"width": 180,
		}
	)
	columns = [first]
	if by_car:
		columns.append({"fieldname": "title", "label": _("Car"), "fieldtype": "Data", "width": 220})
	else:
		columns.append({"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 110})
	columns += [
		{"fieldname": "times", "label": _("Times"), "fieldtype": "Int", "width": 80},
		{"fieldname": "own_workshop", "label": _("Own Workshop"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "outside", "label": _("Outside"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 160},
	]
	return columns, rows
