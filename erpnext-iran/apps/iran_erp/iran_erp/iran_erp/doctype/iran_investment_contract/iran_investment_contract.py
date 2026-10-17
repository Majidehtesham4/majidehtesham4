# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

"""An investor's money in the business for a number of months at a monthly profit rate.

Partnership: the money comes in («واریز به حساب»), the profit is a fixed percent of it each month
and is paid monthly or at the end, and the money itself is paid back at the end. Profit is
counted day by day (amount × monthly rate × 12 ÷ 365 a day), so the investor can see at any time
what they have earned so far. Many investors take cheques for every payment when they hand the
money over: «صدور چک‌ها» issues them all at once.

Reinvestment: payments not yet made can be put back in instead (their cheques are given back),
and money from cleared cheques can be brought back in; either way a new contract continues this
one, so a chain of contracts shows how the money grew.

Car remittance: the investor buys a car's remittance; when the car arrives it is sold at the
business for the investor, and the investor is owed the price less the business's commission.

In the books, what the business owes the investor is in «حساب سرمایه‌گذاران» under the investor:
the money received, and each profit as it falls due (an expense of the business).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, date_diff, flt, getdate, nowdate

from iran_erp.business import account, cancel_entries, journal, party_account, require_cash_account


def daily_profit(amount, monthly_rate):
	return flt(amount) * flt(monthly_rate) / 100 * 12 / 365


class IranInvestmentContract(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Enter the amount"))
		if cint(self.months) <= 0:
			frappe.throw(_("Enter the number of months"))
		require_cash_account(self.received_to, self.company)
		self.end_date = add_months(self.start_date, cint(self.months))
		if self.contract_type == "Car Remittance":
			if not self.vehicle:
				frappe.throw(_("Choose the car of the remittance (make it with status «Awaiting Delivery»)"))
			self.monthly_rate = 0
			self.monthly_profit = self.total_profit = 0
		else:
			self.monthly_profit = flt(flt(self.amount) * flt(self.monthly_rate) / 100, 0)
			self.total_profit = self.monthly_profit * cint(self.months)
		if self.scope == "Vehicle" and not self.vehicle:
			frappe.throw(_("Choose the car the money is invested in"))
		if self.docstatus == 0:
			self.make_schedule()
			self.status = "Draft"
		self.set_summary()

	def make_schedule(self):
		cheques = {(row.kind, str(row.due_date)): row.cheque for row in self.schedule if row.cheque}
		self.schedule = []
		rows = []
		if self.contract_type == "Partnership":
			if self.profit_payment == "Monthly":
				rows = [
					("Profit", add_months(self.start_date, i), self.monthly_profit)
					for i in range(1, cint(self.months) + 1)
				]
			else:
				rows = [("Profit", self.end_date, self.total_profit)]
			rows.append(("Principal", self.end_date, flt(self.amount)))
		for kind, due, amount in rows:
			if flt(amount) > 0:
				self.append(
					"schedule",
					{
						"kind": kind,
						"due_date": due,
						"amount": amount,
						"status": "Pending",
						"cheque": cheques.get((kind, str(due))),
					},
				)

	def set_summary(self, today=None):
		today = getdate(today or nowdate())
		end = min(today, getdate(self.end_date))
		days = max(0, date_diff(end, self.start_date))
		self.accrued_profit = flt(daily_profit(self.amount, self.monthly_rate) * days, 0)
		self.paid_profit = sum(
			flt(r.amount) for r in self.schedule if r.kind == "Profit" and r.status in ("Paid", "Reinvested")
		)

	# ------------------------------------------------------------ submit

	def on_submit(self):
		supplier = self.supplier()
		if self.received_to and not self.parent_contract:
			entry = journal(
				self.company,
				self.start_date,
				[
					{"account": self.received_to, "debit": self.amount},
					{**self.investor_row(supplier), "credit": self.amount},
				],
				_("Investment {0} of {1}").format(self.name, self.investor_name),
				branch=self.branch,
			)
			self.db_set("receipt_entry", entry)
		if self.contract_type == "Car Remittance":
			vehicle = frappe.get_doc("Iran Vehicle", self.vehicle)
			vehicle.ownership, vehicle.investment_contract = "Investor", self.name
			vehicle.flags.ignore_permissions = True
			vehicle.save()
		self.db_set("status", "Active")

	def on_cancel(self):
		cancel_entries(*[row.accrual_entry for row in self.schedule], self.receipt_entry)
		self.db_set("status", "Cancelled")

	def supplier(self):
		return frappe.db.get_value("Iran Investor", self.investor, "supplier")

	def investor_row(self, supplier=None):
		supplier = supplier or self.supplier()
		return {
			"account": party_account("Supplier", supplier, self.company),
			"party_type": "Supplier",
			"party": supplier,
		}

	# ------------------------------------------------------------ while running

	def accrue_profit(self, upto=None, rows=None):
		"""Profit that has fallen due becomes owed to the investor (an expense of the business)."""
		upto = getdate(upto or nowdate())
		rows = rows or [
			r
			for r in self.schedule
			if r.kind == "Profit"
			and not r.accrual_entry
			and r.status == "Pending"
			and getdate(r.due_date) <= upto
		]
		rows = [r for r in rows if r.kind == "Profit" and not r.accrual_entry]
		if not rows:
			return None
		amount = sum(flt(r.amount) for r in rows)
		entry = journal(
			self.company,
			min(upto, max(getdate(r.due_date) for r in rows)),
			[
				{"account": account(self.company, "investor_profit"), "debit": amount},
				{**self.investor_row(), "credit": amount},
			],
			_("Profit of investment {0} of {1}").format(self.name, self.investor_name),
			branch=self.branch,
		)
		for row in rows:
			row.db_set("accrual_entry", entry, update_modified=False)
		return entry

	def update_status(self, today=None):
		today = getdate(today or nowdate())
		cheques = [r.cheque for r in self.schedule if r.cheque]
		statuses = (
			dict(
				frappe.get_all(
					"Iran Cheque", filters={"name": ("in", cheques)}, fields=["name", "status"], as_list=True
				)
			)
			if cheques
			else {}
		)
		for row in self.schedule:
			if row.status == "Pending" and row.cheque and statuses.get(row.cheque) == "Cleared":
				row.db_set("status", "Paid", update_modified=False)
		self.set_summary(today)
		if self.docstatus != 1:
			return
		if self.schedule and all(r.status in ("Paid", "Reinvested") for r in self.schedule):
			status = "Settled"
		elif getdate(self.end_date) <= today:
			status = "Matured"
		else:
			status = "Active"
		self.db_set(
			{"status": status, "accrued_profit": self.accrued_profit, "paid_profit": self.paid_profit},
			update_modified=False,
		)

	def record_vehicle_sale(self, sale):
		"""A remittance car was sold (or its sale cancelled): what the investor is owed."""
		if sale:
			price = flt(sale.sale_price)
			settlement = price - flt(price * flt(self.commission_rate) / 100, 0)
			self.db_set({"sale_amount": price, "settlement_amount": settlement, "status": "Matured"})
			if not any(r.kind == "Principal" for r in self.schedule):
				self.append(
					"schedule",
					{
						"kind": "Principal",
						"due_date": sale.posting_date,
						"amount": settlement,
						"status": "Pending",
					},
				)
				self.schedule[-1].db_insert()
		else:
			self.db_set({"sale_amount": 0, "settlement_amount": 0, "status": "Active"})
			for row in list(self.schedule):
				if row.kind == "Principal" and not row.cheque and row.status == "Pending":
					frappe.delete_doc("Iran Investment Payment", row.name, ignore_permissions=True)

	@frappe.whitelist()
	def get_summary(self):
		self.update_status()
		threshold = flt(frappe.db.get_single_value("Iran ERP Settings", "reinvest_threshold"))
		cleared = sum(flt(r.amount) for r in self.schedule if r.status == "Paid" and not r.reinvested_in)
		return {
			"accrued_profit": self.accrued_profit,
			"paid_profit": self.paid_profit,
			"daily_profit": flt(daily_profit(self.amount, self.monthly_rate), 0),
			"cleared_not_reinvested": cleared,
			"threshold": threshold,
			"reinvest_ready": bool(threshold and cleared >= threshold),
			"chain": self.chain(),
		}

	def chain(self):
		"""The contracts this one continues and those that continue it, oldest first."""
		first = self
		seen = {self.name}
		while first.parent_contract and first.parent_contract not in seen:
			seen.add(first.parent_contract)
			first = frappe.get_doc("Iran Investment Contract", first.parent_contract)
		out = []
		current = [first.name]
		while current:
			rows = frappe.get_all(
				"Iran Investment Contract",
				filters={"name": ("in", current), "docstatus": ("<", 2)},
				fields=["name", "amount", "start_date", "end_date", "monthly_rate", "status"],
				order_by="start_date asc",
			)
			out += rows
			current = frappe.get_all(
				"Iran Investment Contract",
				filters={"parent_contract": ("in", current), "docstatus": ("<", 2)},
				pluck="name",
			)
		return out

	@frappe.whitelist()
	def issue_cheques(
		self,
		bank_account: str,
		first_number: str,
		sayad_ids: str | None = None,
		posting_date: str | None = None,
	):
		"""Issued cheques for every payment still pending without one, numbered on from the first."""
		from iran_erp.utils.national_id import normalize_digits

		self.check_permission("submit")
		if self.docstatus != 1:
			frappe.throw(_("Submit the contract first"))
		number = normalize_digits(first_number or "").strip()
		if not number.isdigit():
			frappe.throw(_("Enter the number of the first cheque"))
		sayad = [s for s in normalize_digits(sayad_ids or "").split() if s]
		supplier = self.supplier()
		width, next_number, made = len(number), int(number), []
		for row in self.schedule:
			if row.cheque or row.status != "Pending":
				continue
			cheque = frappe.get_doc(
				{
					"doctype": "Iran Cheque",
					"cheque_type": "Issued",
					"company": self.company,
					"party_type": "Supplier",
					"party": supplier,
					"cheque_number": str(next_number).zfill(width),
					"sayad_id": sayad[len(made)] if len(made) < len(sayad) else None,
					"amount": row.amount,
					"posting_date": posting_date or nowdate(),
					"due_date": row.due_date,
					"bank_account": bank_account,
					"remarks": _("{0} of investment {1}").format(_(row.kind), self.name),
				}
			)
			cheque.flags.ignore_permissions = True
			cheque.insert()
			cheque.submit()
			row.db_set("cheque", cheque.name)
			made.append(cheque.name)
			next_number += 1
		return made

	@frappe.whitelist()
	def pay(self, row: int, paid_from: str, date: str | None = None):
		"""A payment made by transfer or in cash rather than by cheque."""
		self.check_permission("submit")
		require_cash_account(paid_from, self.company)
		payment = next((r for r in self.schedule if r.idx == cint(row)), None)
		if not payment or payment.status != "Pending" or payment.cheque:
			frappe.throw(_("This payment is not open, or it has a cheque"))
		date = date or nowdate()
		self.accrue_profit(date, rows=[payment])
		journal(
			self.company,
			date,
			[
				{**self.investor_row(), "debit": payment.amount},
				{"account": paid_from, "credit": payment.amount},
			],
			_("{0} of investment {1} paid").format(_(payment.kind), self.name),
			branch=self.branch,
		)
		payment.db_set("status", "Paid")
		self.update_status()

	@frappe.whitelist()
	def reinvest(
		self,
		rows: str | list | None = None,
		months: int | None = None,
		monthly_rate: float | None = None,
		profit_payment: str | None = None,
		cleared_amount: float | None = None,
		received_to: str | None = None,
	):
		"""A new contract that continues this one.

		rows: payments not yet made that are put back in; their cheques, if any, come back.
		cleared_amount: money from cleared cheques the investor brings back in (into received_to).
		"""
		self.check_permission("submit")
		if self.docstatus != 1:
			frappe.throw(_("Submit the contract first"))
		if isinstance(rows, str):
			rows = frappe.parse_json(rows) if rows.strip() else []
		chosen = [r for r in self.schedule if r.idx in {cint(i) for i in rows or []}]
		if any(r.status != "Pending" for r in chosen):
			frappe.throw(_("Only payments not yet made can be put back in"))
		cleared_amount = flt(cleared_amount)
		if cleared_amount and not received_to:
			frappe.throw(_("Choose the account the money is brought back into"))
		amount = sum(flt(r.amount) for r in chosen) + cleared_amount
		if amount <= 0:
			frappe.throw(_("Choose the payments to put back in, or the amount brought back"))

		new = frappe.get_doc(
			{
				"doctype": "Iran Investment Contract",
				"investor": self.investor,
				"company": self.company,
				"contract_type": "Partnership",
				"scope": self.scope if self.scope != "Vehicle" else "Whole Business",
				"branch": self.branch,
				"amount": amount,
				"start_date": nowdate(),
				"months": cint(months) or cint(self.months),
				"monthly_rate": flt(monthly_rate) if monthly_rate is not None else self.monthly_rate,
				"profit_payment": profit_payment or self.profit_payment,
				"parent_contract": self.name,
				"remarks": _("Continues {0}").format(self.name),
			}
		)
		new.flags.ignore_permissions = True
		new.insert()

		# Payments put back in: the profit is owed now, a cheque given for it comes back
		self.accrue_profit(nowdate(), rows=chosen)
		for row in chosen:
			if row.cheque:
				cheque = frappe.get_doc("Iran Cheque", row.cheque)
				if cheque.docstatus == 1 and cheque.status == "Issued":
					cheque.flags.ignore_permissions = True
					cheque.take_action("return", remarks=_("Reinvested in {0}").format(new.name))
			row.db_set({"status": "Reinvested", "reinvested_in": new.name})
		# Money from cleared cheques comes back in
		if cleared_amount:
			journal(
				self.company,
				nowdate(),
				[
					{"account": received_to, "debit": cleared_amount},
					{**self.investor_row(), "credit": cleared_amount},
				],
				_("Reinvestment {0} of {1}").format(new.name, self.investor_name),
				branch=self.branch,
			)
			left = cleared_amount
			for row in self.schedule:
				if left <= 0:
					break
				if row.status == "Paid" and not row.reinvested_in:
					row.db_set("reinvested_in", new.name)
					left -= flt(row.amount)
		self.update_status()
		return new.name
