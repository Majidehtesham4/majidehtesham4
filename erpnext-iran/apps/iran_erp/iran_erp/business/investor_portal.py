"""«حساب من»: an investor's own account, for the investor's login.

An investor sees their contracts, the profit earned on each up to today (day by day), what has
been paid and what is still to come with its cheque, a month-by-month chart of profit and
payments, their cheques, the cars bought with their money and what became of them, and their
statement with the business; nothing of anyone else. Staff who keep the books can open the same
page for any investor.
"""

import re

import frappe
import jdatetime
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from iran_erp.iran_dealership.doctype.iran_investment_contract.iran_investment_contract import (
	daily_profit,
	profit_of,
)

STAFF_ROLES = ("System Manager", "Accounts Manager", "Accounts User")


def _investors(investor: str | None):
	roles = set(frappe.get_roles())
	if roles & set(STAFF_ROLES):
		if investor:
			return [investor]
		return frappe.get_all("Iran Investor", pluck="name", order_by="full_name asc")
	# Anyone else sees only the investor whose login they are
	return frappe.get_all("Iran Investor", filters={"user": frappe.session.user}, pluck="name")


@frappe.whitelist()
def get_my_account(investor: str | None = None) -> dict:
	names = _investors(investor)
	if not names:
		frappe.throw(_("No investor account is linked to your login. Ask the office to link it."))
	staff = bool(set(frappe.get_roles()) & set(STAFF_ROLES))
	investors = []
	for name in names[:1]:
		doc = frappe.get_doc("Iran Investor", name)
		contracts = []
		totals = {"invested": 0, "earned": 0, "paid": 0, "upcoming": 0}
		for contract_name in frappe.get_all(
			"Iran Investment Contract",
			filters={"investor": name, "docstatus": 1},
			pluck="name",
			order_by="start_date desc",
		):
			contract = frappe.get_doc("Iran Investment Contract", contract_name)
			contract.update_status()
			cheques = {
				r.name: r
				for r in frappe.get_all(
					"Iran Cheque",
					filters={"name": ("in", [p.cheque for p in contract.schedule if p.cheque])},
					fields=["name", "cheque_number", "status"],
				)
			}
			payments = [
				{
					"due_date": str(p.due_date),
					"kind": p.kind,
					"amount": flt(p.amount),
					"status": p.status,
					"cheque_number": cheques[p.cheque].cheque_number if p.cheque in cheques else None,
					"cheque_status": cheques[p.cheque].status if p.cheque in cheques else None,
				}
				for p in contract.schedule
			]
			active = contract.status in ("Active", "Matured")
			if active:
				totals["invested"] += flt(contract.amount)
			totals["earned"] += flt(contract.accrued_profit)
			totals["paid"] += sum(p["amount"] for p in payments if p["status"] == "Paid")
			totals["upcoming"] += sum(
				p["amount"]
				for p in payments
				if p["status"] == "Pending" and getdate(p["due_date"]) >= getdate(nowdate())
			)
			contracts.append(
				{
					"name": contract.name,
					"type": contract.contract_type,
					"status": contract.status,
					"amount": flt(contract.amount),
					"start_date": str(contract.start_date),
					"end_date": str(contract.end_date),
					"months": contract.months,
					"monthly_rate": flt(contract.monthly_rate),
					"accrued_profit": flt(contract.accrued_profit),
					"total_profit": flt(contract.total_profit),
					"parent_contract": contract.parent_contract,
					"vehicle": frappe.db.get_value("Iran Vehicle", contract.vehicle, "title")
					if contract.vehicle
					else None,
					"settlement_amount": flt(contract.settlement_amount),
					"payments": payments,
				}
			)
		docs = [frappe.get_doc("Iran Investment Contract", c["name"]) for c in contracts]
		upcoming = sorted(
			(p for c in contracts for p in c["payments"] if p["status"] == "Pending"),
			key=lambda p: p["due_date"],
		)
		totals["profit_promised"] = sum(c["total_profit"] for c in contracts)
		# Everything still to be paid to the investor, due or not
		totals["remaining"] = sum(p["amount"] for p in upcoming)
		totals["profit_received"] = sum(
			profit_of(r) for c in docs for r in c.schedule if r.status in ("Paid", "Reinvested")
		)
		active = [c for c in contracts if c["status"] in ("Active", "Matured") and c["type"] == "Partnership"]
		weight = sum(c["amount"] for c in active)
		totals["annual_rate"] = (
			round(sum(c["amount"] * c["monthly_rate"] for c in active) / weight * 12, 1) if weight else 0
		)
		investors.append(
			{
				"name": doc.name,
				"full_name": doc.full_name,
				"contracts": contracts,
				"totals": totals,
				"next_payment": upcoming[0] if upcoming else None,
				"chart": _chart(docs),
				"cheques": _cheques(docs),
				"cars": _cars(doc.name, docs),
				"statement": _statement(doc.supplier),
			}
		)
	return {
		"investors": investors,
		"staff": staff,
		"choices": frappe.get_all("Iran Investor", fields=["name", "full_name"], order_by="full_name asc")
		if staff
		else [],
	}


def _jalali_key(date):
	j = jdatetime.date.fromgregorian(date=getdate(date))
	return (j.year, j.month)


def _chart(contracts) -> dict:
	"""Month by month (Jalali), from the first contract to the last payment: the profit earned that
	month (day by day), what was paid to the investor and what is still to be paid."""
	if not contracts:
		return {"labels": [], "earned": [], "paid": [], "pending": []}
	start = min(getdate(c.start_date) for c in contracts)
	end = max([getdate(c.end_date) for c in contracts] + [getdate(r.due_date) for c in contracts for r in c.schedule])
	keys, day = [], start
	while day <= end and len(keys) < 48:
		key = _jalali_key(day)
		if key not in keys:
			keys.append(key)
		day = add_days(day, 1)
	index = {k: i for i, k in enumerate(keys)}
	earned, paid, pending = [0.0] * len(keys), [0.0] * len(keys), [0.0] * len(keys)
	today = getdate(nowdate())
	for c in contracts:
		if c.contract_type != "Partnership":
			continue
		per_day = daily_profit(c.amount, c.monthly_rate)
		day, last = getdate(c.start_date), min(getdate(c.end_date), today)
		while day < last:
			key = _jalali_key(day)
			if key in index:
				earned[index[key]] += per_day
			day = add_days(day, 1)
	for c in contracts:
		for r in c.schedule:
			key = _jalali_key(r.due_date)
			if key not in index:
				continue
			if r.status in ("Paid", "Reinvested"):
				paid[index[key]] += flt(r.amount)
			else:
				pending[index[key]] += flt(r.amount)
	labels = [f"{jdatetime.date.j_months_fa[m - 1]} {y}" for y, m in keys]
	return {
		"labels": labels,
		"earned": [round(v) for v in earned],
		"paid": [round(v) for v in paid],
		"pending": [round(v) for v in pending],
		"current": index.get(_jalali_key(today)),
	}


def _cheques(contracts) -> list[dict]:
	names = [r.cheque for c in contracts for r in c.schedule if r.cheque]
	if not names:
		return []
	kinds = {r.cheque: (r.kind, c.name) for c in contracts for r in c.schedule if r.cheque}
	rows = frappe.get_all(
		"Iran Cheque",
		filters={"name": ("in", names)},
		fields=["name", "cheque_number", "sayad_id", "due_date", "amount", "status", "bank_account"],
		order_by="due_date asc",
	)
	for row in rows:
		row.kind, row.contract = kinds.get(row.name, ("", ""))
		row.bank = frappe.db.get_value("Bank Account", row.bank_account, "bank") if row.bank_account else ""
		row.due_date = str(row.due_date)
		row.pop("bank_account")
	return rows


def _cars(investor, contracts) -> list[dict]:
	"""The cars bought with the investor's money (theirs, a remittance, or the car a contract is
	invested in) and what became of each."""
	names = set(frappe.get_all("Iran Vehicle", filters={"investor": investor}, pluck="name"))
	names |= {c.vehicle for c in contracts if c.vehicle}
	cars = []
	for name in names:
		car = frappe.db.get_value(
			"Iran Vehicle",
			name,
			[
				"name", "title", "car_model", "year", "plate", "status", "entry_date", "exit_date",
				"purchase_price", "total_cost", "asking_price", "sold_price", "profit", "investment_contract",
			],
			as_dict=True,
		)  # fmt: skip
		if not car:
			continue
		car.days = date_diff(car.exit_date or nowdate(), car.entry_date) if car.entry_date else 0
		for key in ("entry_date", "exit_date"):
			car[key] = str(car[key]) if car[key] else None
		cars.append(car)
	return sorted(cars, key=lambda c: c.entry_date or "", reverse=True)


def _statement(supplier) -> dict:
	"""The investor's account with the business, from the investor's side: money put in and profit
	owed to them, payments made to them, and what the business owes them after each."""
	if not supplier:
		return {"rows": [], "balance": 0}
	entries = frappe.db.sql(
		"""select posting_date, voucher_type, voucher_no, remarks, sum(credit - debit) as amount
		from `tabGL Entry` where party_type = 'Supplier' and party = %s and is_cancelled = 0
		group by posting_date, voucher_type, voucher_no, remarks order by posting_date, creation""",
		supplier,
		as_dict=True,
	)
	balance, rows = 0.0, []
	for e in entries:
		amount = flt(e.amount)
		if not amount:
			continue
		balance += amount
		rows.append(
			{
				"date": str(e.posting_date),
				"description": _describe(e),
				"in": amount if amount > 0 else 0,
				"out": -amount if amount < 0 else 0,
				"balance": balance,
			}
		)
	return {"rows": rows[-200:], "balance": balance}


CHEQUE_REMARK = re.compile(r"#\s*(\S+)\s+(?:dated|به تاریخ)\s+(\d{1,2})-(\d{1,2})-(\d{4})")


def _describe(entry) -> str:
	"""What a line of the statement was, in words: a cheque given, the money put in, a profit."""
	from iran_erp.utils.jalali import format_jalali

	remarks = entry.remarks or ""
	cheque = CHEQUE_REMARK.search(remarks)
	if cheque:
		number, day, month, year = cheque.groups()
		due = format_jalali(getdate(f"{year}-{month}-{day}"))
		return _("Cheque {0} given to you, due {1}").format(number, due)
	if entry.voucher_type == "Journal Entry":
		remark = frappe.db.get_value("Journal Entry", entry.voucher_no, "user_remark") or ""
		if remark.strip():
			return remark.strip().split("\n")[0][:140]
	if entry.voucher_type == "Payment Entry":
		return _("Payment {0}").format(entry.voucher_no)
	return (remarks.split("\n")[0] or _(entry.voucher_type))[:140]
