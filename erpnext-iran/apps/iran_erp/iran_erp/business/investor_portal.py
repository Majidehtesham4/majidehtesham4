"""«حساب من»: an investor's own account, for the investor's login.

An investor sees their contracts, the profit earned on each up to today (day by day), what has
been paid and what is still to come with its cheque, and nothing of anyone else. Staff who keep
the books can open the same page for any investor.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

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
		investors.append(
			{"name": doc.name, "full_name": doc.full_name, "contracts": contracts, "totals": totals}
		)
	return {
		"investors": investors,
		"staff": staff,
		"choices": frappe.get_all("Iran Investor", fields=["name", "full_name"], order_by="full_name asc")
		if staff
		else [],
	}
