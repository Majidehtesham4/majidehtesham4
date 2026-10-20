"""The dealership's home: the lot at a glance, the cheques and instalments of the coming days,
what is owed to investors this month, month-by-month money, and the latest events of the cars'
files.

Who looks decides what is shown. The general manager (a System Manager, or a manager with no
branch of their own) sees the whole business and each branch beside the others: its cars, the
value of the business's own cars, of the cars left for sale by customers (امانی) and of the
investors' cars, and its sales and profit this month. A branch's manager sees their branch, and
the cars of the other branches they may sell. The values of cars are only for those who may see
the books (not reception).
"""

import frappe
import jdatetime
from frappe.utils import add_days, flt, getdate, nowdate

from iran_erp.business import trade_profile
from iran_erp.iran_dealership.doctype.iran_vehicle.iran_vehicle import is_admin, user_branch

LOT = ("Awaiting Delivery", "In Preparation", "Ready for Sale", "Reserved")

# Month-by-month money, in the order of their colours on the chart
SERIES = (
	"sales",
	"car_profit",
	"interest",
	"service_costs",
	"investor_profit",
	"net",
	"purchases",
	"collected",
)
# Days in the lot, grouped
AGES = ((0, 30), (31, 60), (61, 90), (91, None))
# Whose the cars are: the business's own (its assets, at cost), the investors', and customers'
# cars left for sale (امانی, at their asking price)
OWNERS = ("Business", "Investor", "Customer")


def is_general_manager() -> bool:
	return is_admin() or not user_branch()


def can_see_books() -> bool:
	"""Purchase prices and costs of cars are on the vehicle's second permission level."""
	return 1 in frappe.get_meta("Iran Vehicle").get_permlevel_access("read")


def holdings(branch: str | None = None) -> dict:
	"""For each owner: the cars in the lot, what they cost and what they are offered for."""
	rows = frappe.db.sql(
		"""select ownership, count(*) as count, sum(total_cost) as cost, sum(asking_price) as asking
		from `tabIran Vehicle` where status in %(lot)s {} group by ownership""".format(
			"and branch = %(branch)s" if branch else ""
		),
		{"lot": LOT, "branch": branch},
		as_dict=True,
	)
	found = {r.ownership or "Business": r for r in rows}
	return {
		owner: {
			"count": (found.get(owner) or {}).get("count") or 0,
			"cost": flt((found.get(owner) or {}).get("cost")),
			"asking": flt((found.get(owner) or {}).get("asking")),
		}
		for owner in OWNERS
	}


def by_branch(month_start, month_end) -> list[dict]:
	"""Each branch beside the others: its lot, the value of its cars by owner, its month."""
	lot = frappe.db.sql(
		"""select ifnull(branch, '') as branch, count(*) as cars,
			sum(status = 'Ready for Sale') as ready,
			sum(ownership = 'Business') as business, sum(if(ownership = 'Business', total_cost, 0)) as business_value,
			sum(ownership = 'Investor') as investor, sum(if(ownership = 'Investor', total_cost, 0)) as investor_value,
			sum(ownership = 'Customer') as customer, sum(if(ownership = 'Customer', asking_price, 0)) as customer_value,
			sum(asking_price) as asking
		from `tabIran Vehicle` where status in %(lot)s group by ifnull(branch, '')""",
		{"lot": LOT},
		as_dict=True,
	)
	sales = frappe.db.sql(
		"""select ifnull(branch, '') as branch, count(*) as sold, sum(sale_price) as sales
		from `tabIran Instalment Sale` where docstatus = 1 and posting_date between %s and %s
		group by ifnull(branch, '')""",
		(month_start, month_end),
		as_dict=True,
	)
	# The profit on each car sold this month, as its file shows it
	profit = frappe.db.sql(
		"""select ifnull(s.branch, '') as branch, sum(v.profit) as profit
		from `tabIran Instalment Sale` s join `tabIran Vehicle` v on v.name = s.vehicle
		where s.docstatus = 1 and s.posting_date between %s and %s group by ifnull(s.branch, '')""",
		(month_start, month_end),
		as_dict=True,
	)
	rows = {r.branch: {**r} for r in lot}
	for extra in (sales, profit):
		for r in extra:
			rows.setdefault(r.branch, {"branch": r.branch}).update(r)
	for name in frappe.get_all("Branch", pluck="name"):
		rows.setdefault(name, {"branch": name})
	keys = ("cars", "ready", "business", "business_value", "investor", "investor_value", "customer")
	keys += ("customer_value", "asking", "sold", "sales", "profit")
	out = [{"branch": b, **{k: flt(r.get(k)) for k in keys}} for b, r in rows.items()]
	return sorted(out, key=lambda r: (not r["branch"], -r["cars"], r["branch"]))


@frappe.whitelist()
def get_dashboard(branch: str | None = None, months: int = 12) -> dict:
	frappe.has_permission("Iran Vehicle", throw=True)
	# A branch's staff see their own branch; the general manager sees all, or chooses one
	general = is_general_manager()
	branch = (branch if general else (user_branch() or branch)) or None
	books = can_see_books()
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
			where status in %(lot)s and ownership = 'Business' {}""".format(
				"and branch = %(branch)s" if branch else ""
			),
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
	ages = [0] * len(AGES)
	for car in frappe.get_all(
		"Iran Vehicle", filters={**where, "status": ("in", LOT)}, fields=["entry_date"]
	):
		days = (today - getdate(car.entry_date)).days if car.entry_date else 0
		ages[next(i for i, (_low, high) in enumerate(AGES) if high is None or days <= high)] += 1
	capacity = dict(frappe.get_all("Iran Parking", fields=["name", "capacity"], as_list=True))
	for row in parkings:
		row.capacity = capacity.get(row.parking) or 0
	money = monthly(branch, min(max(int(months or 12), 3), 24))
	this_month, last_month = (
		{key: values[-1] for key, values in money["series"].items()},
		{key: values[-2] for key, values in money["series"].items()},
	)
	return {
		"trade_name": trade_profile().name,
		"today": f"{j.day} {j.j_months_fa[j.month - 1]} {j.year}",
		"months": money,
		"this_month": this_month,
		"last_month": last_month,
		"ages": [
			{"from": low, "to": high, "count": count} for (low, high), count in zip(AGES, ages, strict=True)
		],
		"branch": branch,
		"is_admin": is_admin(),
		"is_general": general,
		"books": books,
		"holdings": holdings(branch) if books else None,
		"branches": by_branch(month_start, add_days(next_month, -1)) if general and books else [],
		# A branch's manager may sell the other branches' cars: how many each has ready
		"other_branches": []
		if general
		else frappe.get_all(
			"Iran Vehicle",
			filters={"status": ("in", LOT), "branch": ("!=", branch or "")},
			fields=["branch", {"COUNT": "*", "as": "count"}],
			group_by="branch",
		),
		"counts": {status: counts.get(status, 0) for status in LOT},
		"in_lot": sum(counts.values()),
		"stock_value": stock_value if books else None,
		"sold_month": sold_month,
		"cheques_in": {"count": cheques_in[0] or 0, "amount": flt(cheques_in[1])},
		"cheques_out": {"count": cheques_out[0] or 0, "amount": flt(cheques_out[1])},
		"overdue": {"count": overdue[0] or 0, "amount": flt(overdue[1])},
		"investors_month": flt(investors_month),
		"requests": frappe.db.count("Iran Car Inquiry", {**where, "status": "New"}),
		"parkings": parkings,
		"oldest": oldest,
		"events": events,
	}


def monthly(branch: str | None, count: int) -> dict:
	"""The last `count` Jalali months, this one last: sales, profits, costs and cash of each."""
	today = jdatetime.date.fromgregorian(date=getdate(nowdate()))
	keys = []
	year, month = today.year, today.month
	for _i in range(count):
		keys.insert(0, (year, month))
		year, month = (year - 1, 12) if month == 1 else (year, month - 1)
	start = jdatetime.date(*keys[0], 1).togregorian()
	index = {key: i for i, key in enumerate(keys)}
	series = {key: [0.0] * count for key in SERIES}

	def add(key, date, amount):
		if not date:
			return
		j = jdatetime.date.fromgregorian(date=getdate(date))
		i = index.get((j.year, j.month))
		if i is not None:
			series[key][i] += flt(amount)

	on_branch = {"branch": branch} if branch else {}
	values = {"start": start, "branch": branch}
	branch_of = lambda alias: f"and {alias}.branch = %(branch)s" if branch else ""  # noqa: E731

	for sale in frappe.db.sql(
		f"""select s.posting_date, s.sale_price, v.profit from `tabIran Instalment Sale` s
		left join `tabIran Vehicle` v on v.name = s.vehicle
		where s.docstatus = 1 and s.posting_date >= %(start)s {branch_of("s")}""",
		values,
		as_dict=True,
	):
		add("sales", sale.posting_date, sale.sale_price)
		add("car_profit", sale.posting_date, sale.profit)
	for row in frappe.db.sql(
		f"""select i.paid_date, i.amount, i.interest from `tabIran Instalment` i
		join `tabIran Instalment Sale` s on s.name = i.parent
		where s.docstatus = 1 and i.status in ('Paid', 'Settled Early') and i.paid_date >= %(start)s
		{branch_of("s")}""",
		values,
		as_dict=True,
	):
		add("interest", row.paid_date, row.interest)
		add("collected", row.paid_date, row.amount)
	for row in frappe.db.sql(
		f"""select c.date, c.amount from `tabIran Vehicle Cost` c
		join `tabIran Vehicle` v on v.name = c.parent
		where c.status = 'Done' and c.date >= %(start)s {branch_of("v")}""",
		values,
		as_dict=True,
	):
		add("service_costs", row.date, row.amount)
	for row in frappe.db.sql(
		"""select p.due_date, if(p.kind = 'Profit', p.amount, p.profit_part) as amount
		from `tabIran Investment Payment` p
		join `tabIran Investment Contract` c on c.name = p.parent
		where c.docstatus = 1 and p.kind in ('Profit', 'Profit and Principal')
		and p.due_date >= %(start)s""",
		values,
		as_dict=True,
	):
		add("investor_profit", row.due_date, row.amount)
	for car in frappe.get_all(
		"Iran Vehicle",
		filters={**on_branch, "ownership": "Business"},
		fields=["purchase_date", "entry_date", "purchase_price"],
	):
		add("purchases", car.purchase_date or car.entry_date, car.purchase_price)
	series["net"] = [
		profit + interest - investors
		for profit, interest, investors in zip(
			series["car_profit"], series["interest"], series["investor_profit"], strict=True
		)
	]
	labels = [f"{jdatetime.date.j_months_fa[month - 1]} {year}" for year, month in keys]
	return {"labels": labels, "series": {key: [round(v) for v in values] for key, values in series.items()}}


@frappe.whitelist()
def get_lot_cars(branch: str | None = None, ownership: str | None = None) -> list[dict]:
	"""The cars in the lot with their price and description, for the lists the dashboard opens.

	What a car cost is shown to the general manager, and to a branch's manager for their own
	branch's cars; the price asked for every car is shown to all who may see the books.
	"""
	frappe.has_permission("Iran Vehicle", throw=True)
	if not can_see_books():
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	filters = {"status": ("in", LOT)}
	if branch is not None:
		filters["branch"] = branch or ("is", "not set")
	if ownership in OWNERS:
		filters["ownership"] = ownership
	general, mine = is_general_manager(), user_branch()
	cars = frappe.get_all(
		"Iran Vehicle",
		filters=filters,
		fields=[
			"name", "title", "car_model", "year", "made_in", "color", "plate", "mileage", "status",
			"branch", "ownership", "investor", "owner_customer", "entry_date", "total_cost", "asking_price",
		],
		order_by="branch asc, entry_date asc",
	)  # fmt: skip
	today = getdate(nowdate())
	for car in cars:
		car.days = (today - getdate(car.entry_date)).days if car.entry_date else 0
		if not (general or (mine and car.branch == mine)):
			car.total_cost = None
		car.owner_name = (
			frappe.db.get_value("Iran Investor", car.investor, "full_name")
			if car.ownership == "Investor"
			else frappe.db.get_value("Customer", car.owner_customer, "customer_name")
			if car.ownership == "Customer"
			else ""
		)
		car.pop("investor")
		car.pop("owner_customer")
	return cars
