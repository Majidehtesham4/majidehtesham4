# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

"""A sale paid in instalments, as car dealerships sell: a down payment, then monthly instalments,
usually each one a cheque.

The profit is a flat monthly rate on the financed amount: a car of 2 billion with 1 billion down
leaves 1 billion financed; at 6% a month for 10 months that is 600 million of profit, so the ten
instalments together are 1.6 billion (other costs added to the instalments are financed too).

In the books, the sale is income when the contract is submitted, but the profit is not: it waits
in «سود تحقق‌نیافته فروش اقساطی» and becomes income instalment by instalment as each falls due.
A received cheque for an instalment moves that amount from the customer to cheques receivable,
as any received cheque does (Iran Cheque).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, date_diff, flt, getdate, nowdate

from iran_erp.business import account, cancel_entries, journal, party_account, require_cash_account

ROUND_TO = 1000


def calculate(sale_price, down_payment, other_costs, monthly_rate, months, interval_months=1):
	"""Amounts of a contract: financed, total profit, total of the instalments, and each instalment
	with its principal and profit. Amounts are whole thousands of rials; what rounding leaves over
	goes on the last instalment."""
	months = cint(months)
	interval_months = cint(interval_months) or 1
	if months <= 0:
		frappe.throw(_("Enter the number of instalments"))
	financed = flt(sale_price) - flt(down_payment) + flt(other_costs)
	if financed <= 0:
		frappe.throw(_("The down payment covers the whole price; nothing is left for instalments"))
	interest = flt(financed * flt(monthly_rate) / 100 * months * interval_months, 0)
	total = financed + interest

	def split(amount):
		each = (amount // months // ROUND_TO) * ROUND_TO
		return [each] * (months - 1) + [amount - each * (months - 1)]

	amounts, principals = split(total), split(financed)
	rows = [
		{"amount": amount, "principal": principal, "interest": amount - principal}
		for amount, principal in zip(amounts, principals, strict=True)
	]
	return {"financed": financed, "interest": interest, "total": total, "rows": rows}


class IranInstalmentSale(Document):
	def validate(self):
		if self.vehicle:
			vehicle = frappe.db.get_value(
				"Iran Vehicle",
				self.vehicle,
				["title", "status", "company", "sale_contract", "branch"],
				as_dict=True,
			)
			if vehicle.sale_contract and vehicle.sale_contract != self.name:
				frappe.throw(_("Car {0} is already sold in {1}").format(vehicle.title, vehicle.sale_contract))
			if vehicle.company != self.company:
				frappe.throw(_("Car {0} belongs to another company").format(vehicle.title))
			self.description = self.description or vehicle.title
			self.branch = self.branch or vehicle.branch
		require_cash_account(self.down_payment_account, self.company)
		result = calculate(
			self.sale_price,
			self.down_payment,
			self.other_costs,
			self.monthly_rate,
			self.months,
			self.interval_months,
		)
		self.financed_amount = result["financed"]
		self.total_interest = result["interest"]
		self.total_payable = result["total"]
		self.instalment_amount = result["rows"][0]["amount"]
		if self.docstatus == 0:
			self.make_schedule(result["rows"])
			self.status = "Draft"
		self.set_totals()

	def make_schedule(self, rows):
		cheques = {row.idx: row.cheque for row in self.schedule if row.cheque}
		self.schedule = []
		for i, row in enumerate(rows):
			self.append(
				"schedule",
				{
					**row,
					"due_date": add_months(self.first_due_date, i * (cint(self.interval_months) or 1)),
					"status": "Unpaid",
					"cheque": cheques.get(i + 1),
				},
			)

	def set_totals(self):
		self.paid_total = sum(flt(r.amount) for r in self.schedule if r.status == "Paid")
		self.outstanding = sum(flt(r.amount) for r in self.schedule if r.status in ("Unpaid", "Overdue"))

	# ------------------------------------------------------------ submit

	def on_submit(self):
		receivable = party_account("Customer", self.customer, self.company)
		customer = {"party_type": "Customer", "party": self.customer}
		rows = [
			{
				"account": receivable,
				**customer,
				"debit": flt(self.sale_price) + flt(self.other_costs) + flt(self.total_interest),
			},
			{"account": account(self.company, "deferred_interest"), "credit": self.total_interest},
			{"account": account(self.company, "fee_income"), "credit": self.other_costs},
		]
		rows += self.sale_rows()
		if flt(self.down_payment) and self.down_payment_account:
			rows += [
				{"account": self.down_payment_account, "debit": self.down_payment},
				{"account": receivable, **customer, "credit": self.down_payment},
			]
		entry = journal(
			self.company,
			self.posting_date,
			rows,
			_("Instalment sale {0} to {1}: {2}").format(
				self.name, self.customer_name, self.description or ""
			),
			branch=self.branch,
		)
		self.db_set({"sale_entry": entry, "status": "Active"})
		if self.vehicle:
			self.update_vehicle(sold=True)
		self.update_status()

	def sale_rows(self):
		"""The price: income of the business; or, for a car of an investor or of a customer who left
		it to be sold, owed to that owner less the business's commission. The value of a car the
		business owned is the cost of the sale."""
		price = flt(self.sale_price)
		vehicle = self.vehicle and frappe.get_doc("Iran Vehicle", self.vehicle)
		if vehicle and vehicle.ownership in ("Investor", "Customer"):
			rate = flt(vehicle.commission_rate)
			if not rate and vehicle.investment_contract:
				rate = flt(
					frappe.db.get_value(
						"Iran Investment Contract", vehicle.investment_contract, "commission_rate"
					)
				)
			commission = flt(price * rate / 100, 0)
			return [
				{"account": account(self.company, "commission_income"), "credit": commission},
				{**vehicle.owner_party_row(), "credit": price - commission},
			]
		rows = [
			{"account": account(self.company, "vehicle_sales" if vehicle else "fee_income"), "credit": price}
		]
		if vehicle and flt(vehicle.total_cost):
			rows += [
				{"account": account(self.company, "cost_of_sales"), "debit": vehicle.total_cost},
				{"account": account(self.company, "vehicle_stock"), "credit": vehicle.total_cost},
			]
		return rows

	def update_vehicle(self, sold):
		vehicle = frappe.get_doc("Iran Vehicle", self.vehicle)
		vehicle.mark_sold(self, sold)
		if vehicle.ownership == "Investor" and vehicle.investment_contract:
			frappe.get_doc("Iran Investment Contract", vehicle.investment_contract).record_vehicle_sale(
				self if sold else None
			)

	def on_cancel(self):
		cancel_entries(
			self.settlement_entry,
			*[row.interest_entry for row in self.schedule],
			self.sale_entry,
		)
		self.db_set("status", "Cancelled")
		if self.vehicle:
			self.update_vehicle(sold=False)

	# ------------------------------------------------------------ while running

	def update_status(self, today=None):
		"""Each instalment is paid when its cheque has cleared (or it was paid by hand), overdue when
		its date has passed; the contract is settled when nothing is left."""
		today = getdate(today or nowdate())
		statuses = {}
		cheques = [row.cheque for row in self.schedule if row.cheque]
		if cheques:
			statuses = dict(
				frappe.get_all(
					"Iran Cheque", filters={"name": ("in", cheques)}, fields=["name", "status"], as_list=True
				)
			)
		for row in self.schedule:
			if row.status in ("Paid", "Settled Early"):
				continue
			if row.cheque and statuses.get(row.cheque) == "Cleared":
				row.status, row.paid_date = "Paid", today
			else:
				row.status = "Overdue" if getdate(row.due_date) < today else "Unpaid"
			row.db_set({"status": row.status, "paid_date": row.paid_date}, update_modified=False)
		self.set_totals()
		if self.docstatus == 1:
			open_rows = [r for r in self.schedule if r.status in ("Unpaid", "Overdue")]
			status = (
				"Settled"
				if not open_rows
				else "Overdue"
				if any(r.status == "Overdue" for r in open_rows)
				else "Active"
			)
			self.db_set(
				{"status": status, "paid_total": self.paid_total, "outstanding": self.outstanding},
				update_modified=False,
			)

	def recognize_interest(self, upto=None):
		"""Moves the profit of the instalments that have fallen due to income."""
		upto = getdate(upto or nowdate())
		rows = [
			r
			for r in self.schedule
			if not r.interest_entry
			and flt(r.interest)
			and r.status != "Settled Early"
			and getdate(r.due_date) <= upto
		]
		if not rows:
			return None
		amount = sum(flt(r.interest) for r in rows)
		entry = journal(
			self.company,
			max(getdate(r.due_date) for r in rows),
			[
				{"account": account(self.company, "deferred_interest"), "debit": amount},
				{"account": account(self.company, "instalment_income"), "credit": amount},
			],
			_("Profit of instalments of {0} that fell due").format(self.name),
			branch=self.branch,
		)
		for row in rows:
			row.db_set("interest_entry", entry, update_modified=False)
		return entry

	def late_fee_due(self, today=None):
		"""Late fee of the overdue instalments until today, day by day: amount × monthly rate ÷ 30."""
		today = getdate(today or nowdate())
		rate = flt(self.late_fee_rate) / 100 / 30
		total = 0
		for row in self.schedule:
			if row.status in ("Unpaid", "Overdue") and getdate(row.due_date) < today:
				total += flt(row.amount) * rate * date_diff(today, row.due_date)
		return flt(total, 0)

	@frappe.whitelist()
	def get_summary(self):
		self.update_status()
		today = getdate(nowdate())
		return {
			"late_fee_due": self.late_fee_due(today),
			"late_fee_to_charge": max(0, self.late_fee_due(today) - flt(self.late_fee_billed)),
			"settlement": self.settlement_quote(today) if self.docstatus == 1 and self.outstanding else None,
			"overdue": sum(1 for r in self.schedule if r.status == "Overdue"),
		}

	@frappe.whitelist()
	def charge_late_fees(self, date=None):
		self.check_permission("submit")
		date = date or nowdate()
		amount = self.late_fee_due(date) - flt(self.late_fee_billed)
		if amount <= 0:
			frappe.throw(_("There is no late fee to charge"))
		journal(
			self.company,
			date,
			[
				{
					"account": party_account("Customer", self.customer, self.company),
					"party_type": "Customer",
					"party": self.customer,
					"debit": amount,
				},
				{"account": account(self.company, "fee_income"), "credit": amount},
			],
			_("Late fee of instalments of {0}").format(self.name),
			branch=self.branch,
		)
		self.db_set("late_fee_billed", flt(self.late_fee_billed) + amount)
		return amount

	@frappe.whitelist()
	def mark_paid(self, row: int, paid_to: str, date: str | None = None):
		"""An instalment paid in cash or by transfer rather than by its cheque."""
		self.check_permission("submit")
		require_cash_account(paid_to, self.company)
		instalment = next((r for r in self.schedule if r.idx == cint(row)), None)
		if not instalment or instalment.status not in ("Unpaid", "Overdue"):
			frappe.throw(_("This instalment is not open"))
		if instalment.cheque:
			frappe.throw(_("This instalment has a cheque; clear the cheque instead"))
		journal(
			self.company,
			date or nowdate(),
			[
				{"account": paid_to, "debit": instalment.amount},
				{
					"account": party_account("Customer", self.customer, self.company),
					"party_type": "Customer",
					"party": self.customer,
					"credit": instalment.amount,
				},
			],
			_("Instalment {0} of {1}").format(instalment.idx, self.name),
			branch=self.branch,
		)
		instalment.db_set({"status": "Paid", "paid_date": date or nowdate()})
		self.update_status()

	def settlement_quote(self, date=None):
		"""Paying everything left today: the principal still owed and the profit earned up to today,
		day by day; the profit of the days not yet reached is not charged."""
		date = getdate(date or nowdate())
		open_rows = [r for r in self.schedule if r.status in ("Unpaid", "Overdue")]
		principal = sum(flt(r.principal) for r in open_rows)
		earned = 0
		previous = getdate(self.posting_date)
		for row in self.schedule:
			due = getdate(row.due_date)
			if row in open_rows:
				if due <= date:
					earned += flt(row.interest)
				elif previous < date:
					earned += flt(row.interest) * date_diff(date, previous) / max(1, date_diff(due, previous))
			previous = due
		earned = flt(earned, 0)
		total_interest = sum(flt(r.interest) for r in open_rows)
		return {
			"principal": principal,
			"earned_interest": earned,
			"discount": total_interest - earned,
			"payable": principal + earned,
		}

	@frappe.whitelist()
	def settle_early(self, date=None):
		"""The customer pays everything left now: the profit of the days not reached is taken off
		what they owe. The open instalments are closed; their cheques are to be given back."""
		self.check_permission("submit")
		date = date or nowdate()
		quote = self.settlement_quote(date)
		if not quote["principal"]:
			frappe.throw(_("Nothing is left to settle"))
		self.recognize_interest(date)
		open_rows = [r for r in self.schedule if r.status in ("Unpaid", "Overdue")]
		not_due = sum(flt(r.interest) for r in open_rows if not r.interest_entry)
		receivable = party_account("Customer", self.customer, self.company)
		customer = {"party_type": "Customer", "party": self.customer}
		entry = journal(
			self.company,
			date,
			[
				{"account": account(self.company, "deferred_interest"), "debit": not_due},
				{"account": receivable, **customer, "credit": quote["discount"]},
				{
					"account": account(self.company, "instalment_income"),
					"credit": not_due - quote["discount"],
				},
			],
			_("Early settlement of {0}").format(self.name),
			branch=self.branch,
		)
		for row in open_rows:
			row.db_set({"status": "Settled Early", "interest_entry": row.interest_entry or entry})
		self.db_set({"settlement_entry": entry, "status": "Settled"})
		return quote

	@frappe.whitelist()
	def make_cheques(
		self, bank: str, first_number: str, sayad_ids: str | None = None, branch_name: str | None = None
	):
		"""Received cheques for the instalments that have none, numbered on from the first number."""
		from iran_erp.utils.national_id import normalize_digits

		self.check_permission("submit")
		if self.docstatus != 1:
			frappe.throw(_("Submit the contract first"))
		number = normalize_digits(first_number or "").strip()
		if not number.isdigit():
			frappe.throw(_("Enter the number of the first cheque"))
		sayad = [s for s in normalize_digits(sayad_ids or "").split() if s]
		made = []
		width = len(number)
		next_number = int(number)
		for row in self.schedule:
			if row.cheque or row.status not in ("Unpaid", "Overdue"):
				continue
			cheque = frappe.get_doc(
				{
					"doctype": "Iran Cheque",
					"cheque_type": "Received",
					"company": self.company,
					"party_type": "Customer",
					"party": self.customer,
					"cheque_number": str(next_number).zfill(width),
					"sayad_id": sayad[len(made)] if len(made) < len(sayad) else None,
					"amount": row.amount,
					# Cheques are handed over when the contract is signed
					"posting_date": self.posting_date,
					"due_date": row.due_date,
					"drawer_bank": bank,
					"drawer_branch": branch_name,
					"remarks": _("Instalment {0} of {1}").format(row.idx, self.name),
				}
			)
			cheque.flags.ignore_permissions = True
			cheque.insert()
			cheque.submit()
			row.db_set("cheque", cheque.name)
			made.append(cheque.name)
			next_number += 1
		return made
