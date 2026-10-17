"""The dealership's home: the lot at a glance, the cheques and instalments of the coming days,
what is owed to investors this month, and the latest events of the cars' files."""

import frappe
import jdatetime
from frappe.utils import add_days, flt, getdate, nowdate

from iran_erp.iran_dealership.doctype.iran_vehicle.iran_vehicle import is_admin, user_branch

LOT = ("Awaiting Delivery", "In Preparation", "Ready for Sale", "Reserved")


@frappe.whitelist()
def get_dashboard(branch: str | None = None) -> dict:
	frappe.has_permission("Iran Vehicle", throw=True)
	# Staff see their own branch; an administrator chooses
	branch = branch if is_admin() else (user_branch() or branch)
	where = {"branch": branch} if branch else {}
	today = getdate(nowdate())
	j = jdatetime.date.fromgregorian(date=today)
	month_start = jdatetime.date(j.year, j.month, 1).togregorian()
	next_month = jdatetime.date(j.year + (j.month == 12), j.month % 12 + 1, 1).togregorian()
	week_end = add_days(today, 7)

	counts = dict(
		frappe.get_all(
			"Iran Vehicle",
			filters={**where, "status": ("in", LOT)},
			fields=["status", {"COUNT": "*", "as": "count"}],
			group_by="status",
			as_list=True,
		)
	)
	stock_value = flt(
		frappe.db.sql(
			"""select sum(total_cost) from `tabIran Vehicle`
			where status in %(lot)s and ownership = 'Business' {}""".format("and branch = %(branch)s" if branch else ""),
			{"lot": LOT, "branch": branch},
		)[0][0]
	)
	sold_month = frappe.db.count(
		"Iran Instalment Sale",
		{**where, "docstatus": 1, "posting_date": ("between", (month_start, add_days(next_month, -1)))},
	)
	def cheques(cheque_type, statuses):
		return frappe.db.sql(
			"""select count(*), sum(amount) from `tabIran Cheque` where cheque_type = %s and docstatus = 1
			and status in %s and due_date between %s and %s""",
			(cheque_type, statuses, today, week_end),
		)[0]

	cheques_in = cheques("Received", ("In Hand", "Deposited"))
	cheques_out = cheques("Issued", ("Issued",))
	overdue = frappe.db.sql(
		"""select count(*), sum(i.amount) from `tabIran Instalment` i
		join `tabIran Instalment Sale` s on s.name = i.parent
		where s.docstatus = 1 and i.status in ('Unpaid', 'Overdue') and i.due_date < %(today)s
		{}""".format("and s.branch = %(branch)s" if branch else ""),
		{"today": today, "branch": branch},
	)[0]
	investors_month = frappe.db.sql(
		"""select sum(p.amount) from `tabIran Investment Payment` p
		join `tabIran Investment Contract` c on c.name = p.parent
		where c.docstatus = 1 and p.status = 'Pending' and p.due_date between %(start)s and %(end)s""",
		{"start": month_start, "end": add_days(next_month, -1)},
	)[0][0]
	parkings = frappe.get_all(
		"Iran Vehicle",
		filters={**where, "status": ("in", LOT)},
		fields=["parking", {"COUNT": "*", "as": "count"}],
		group_by="parking",
		order_by="count desc",
	)
	oldest = frappe.get_all(
		"Iran Vehicle",
		filters={**where, "status": ("in", LOT)},
		fields=["name", "title", "entry_date", "status", "asking_price"],
		order_by="entry_date asc",
		limit=6,
	)
	for row in oldest:
		row.days = (today - getdate(row.entry_date)).days if row.entry_date else 0
	events = frappe.db.sql(
		"""select l.parent, v.title, l.event, l.details, l.date
		from `tabIran Vehicle Log` l join `tabIran Vehicle` v on v.name = l.parent
		{} order by l.date desc limit 10""".format("where v.branch = %(branch)s" if branch else ""),
		{"branch": branch},
		as_dict=True,
	)
	return {
		"branch": branch,
		"is_admin": is_admin(),
		"counts": {status: counts.get(status, 0) for status in LOT},
		"in_lot": sum(counts.values()),
		"stock_value": stock_value,
		"sold_month": sold_month,
		"cheques_in": {"count": cheques_in[0] or 0, "amount": flt(cheques_in[1])},
		"cheques_out": {"count": cheques_out[0] or 0, "amount": flt(cheques_out[1])},
		"overdue": {"count": overdue[0] or 0, "amount": flt(overdue[1])},
		"investors_month": flt(investors_month),
		"parkings": parkings,
		"oldest": oldest,
		"events": events,
	}
