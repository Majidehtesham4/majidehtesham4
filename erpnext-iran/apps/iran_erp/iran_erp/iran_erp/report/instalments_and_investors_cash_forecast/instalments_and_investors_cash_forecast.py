"""Month by month (Jalali): the instalments due to come in against what is due to investors, and
the cash left over, so a month that runs short shows up in time."""

import frappe
import jdatetime
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from iran_erp.utils.words import MONTHS


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start = jdatetime.date.fromgregorian(date=getdate(filters.from_date or nowdate()))
	months = cint(filters.months) or 12
	buckets = []
	year, month = start.year, start.month
	for _i in range(months):
		next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
		buckets.append(
			{
				"label": f"{MONTHS[month - 1]} {year}",
				"from": jdatetime.date(year, month, 1).togregorian(),
				"to": jdatetime.date(next_year, next_month, 1).togregorian(),
			}
		)
		year, month = next_year, next_month

	def sums(query_rows):
		out = [0] * len(buckets)
		for due, amount in query_rows:
			due = getdate(due)
			for i, b in enumerate(buckets):
				if b["from"] <= due < b["to"]:
					out[i] += flt(amount)
					break
		# Everything already past due counts in the first month
		for due, amount in query_rows:
			if getdate(due) < buckets[0]["from"]:
				out[0] += flt(amount)
		return out

	conditions = {"company": filters.company} if filters.company else {}
	if filters.branch:
		conditions["branch"] = filters.branch
	incoming = frappe.db.sql(
		"""select i.due_date, i.amount from `tabIran Instalment` i
		join `tabIran Instalment Sale` s on s.name = i.parent
		where s.docstatus = 1 and i.status in ('Unpaid', 'Overdue') {}""".format(
			"".join(f" and s.{k} = %({k})s" for k in conditions)
		),
		conditions,
	)
	outgoing = frappe.db.sql(
		"""select p.due_date, p.amount from `tabIran Investment Payment` p
		join `tabIran Investment Contract` c on c.name = p.parent
		where c.docstatus = 1 and p.status = 'Pending' {}""".format(
			"".join(f" and c.{k} = %({k})s" for k in conditions)
		),
		conditions,
	)
	ins, outs = sums(incoming), sums(outgoing)
	data, running = [], 0
	for i, b in enumerate(buckets):
		running += ins[i] - outs[i]
		data.append(
			{
				"month": b["label"],
				"incoming": ins[i],
				"outgoing": outs[i],
				"net": ins[i] - outs[i],
				"running": running,
			}
		)
	# The total of the running balance is the balance at the end, not the sum of the months
	data.append(
		{
			"month": _("Total"),
			"incoming": sum(ins),
			"outgoing": sum(outs),
			"net": sum(ins) - sum(outs),
			"running": running,
			"bold": 1,
		}
	)
	columns = [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 140},
		{"fieldname": "incoming", "label": _("Instalments Coming In"), "fieldtype": "Currency", "width": 180},
		{"fieldname": "outgoing", "label": _("Due to Investors"), "fieldtype": "Currency", "width": 180},
		{"fieldname": "net", "label": _("Net"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "running", "label": _("Running Balance"), "fieldtype": "Currency", "width": 170},
	]
	chart = {
		"data": {
			"labels": [d["month"] for d in data],
			"datasets": [
				{"name": _("Instalments Coming In"), "values": ins},
				{"name": _("Due to Investors"), "values": outs},
			],
		},
		"type": "bar",
		"colors": ["#0f766e", "#b45309"],
		"fieldtype": "Currency",
	}
	return columns, data, None, chart
