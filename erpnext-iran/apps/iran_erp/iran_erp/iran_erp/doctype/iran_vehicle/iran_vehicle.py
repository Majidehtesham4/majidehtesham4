# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

"""A car of a dealership: what it cost (price and every repair, inspection or transfer fee), who
owns it, and what it was sold for.

A car the business bought is stock of the business: the purchase and each cost are entered in
the books as the car's value («موجودی خودرو»), and when it is sold that value is the cost of the
sale. A car bought with an investor's money for the investor (a remittance) is the investor's:
nothing of it is in the business's stock, and its sale price is owed to the investor less the
business's commission.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from iran_erp.business import account, journal, require_cash_account


class IranVehicle(Document):
	def validate(self):
		self.title = " ".join(str(part) for part in (self.model, self.year, self.color) if part)
		if self.plate:
			self.title += f" - {self.plate}"
		require_cash_account(self.paid_from, self.company)
		for row in self.costs:
			require_cash_account(row.paid_from, self.company)
		if self.ownership == "Investor":
			if self.purchase_entry:
				frappe.throw(
					_("A car whose purchase is in the business's books cannot belong to an investor")
				)
		self.total_cost = flt(self.purchase_price) + sum(flt(row.amount) for row in self.costs)
		if self.sold_price:
			self.profit = flt(self.sold_price) - (self.total_cost if self.ownership == "Business" else 0)

	def on_update(self):
		# Costs paid from a bank or cash account go into the books as soon as they are saved
		if self.ownership != "Business":
			return
		changed = False
		for row in self.costs:
			if row.paid_from and not row.journal_entry and flt(row.amount) > 0:
				row.journal_entry = journal(
					self.company,
					row.date or nowdate(),
					[
						{"account": account(self.company, "vehicle_stock"), "debit": row.amount},
						{"account": row.paid_from, "credit": row.amount},
					],
					_("Cost of car {0}: {1}").format(self.title, row.description),
					branch=self.branch,
				)
				row.db_set("journal_entry", row.journal_entry)
				changed = True
		if changed:
			self.notify_update()

	def on_trash(self):
		if self.purchase_entry or any(row.journal_entry for row in self.costs) or self.sale_contract:
			frappe.throw(_("This car is in the books; it cannot be deleted"))

	@frappe.whitelist()
	def record_purchase(self):
		"""The purchase in the books: the car's value against the seller or the account paid from."""
		self.check_permission("write")
		if self.purchase_entry:
			frappe.throw(_("The purchase is already recorded"))
		if self.ownership != "Business":
			frappe.throw(_("Only a car the business owns is recorded as its stock"))
		if flt(self.purchase_price) <= 0:
			frappe.throw(_("Enter the purchase price first"))
		if self.seller:
			from iran_erp.business import party_account

			credit = {
				"account": party_account("Supplier", self.seller, self.company),
				"party_type": "Supplier",
				"party": self.seller,
			}
		elif self.paid_from:
			credit = {"account": self.paid_from}
		else:
			frappe.throw(_("Choose who the car was bought from, or the account it was paid from"))
		entry = journal(
			self.company,
			self.purchase_date or nowdate(),
			[
				{"account": account(self.company, "vehicle_stock"), "debit": self.purchase_price},
				{**credit, "credit": self.purchase_price},
			],
			_("Purchase of car {0}").format(self.title),
			branch=self.branch,
		)
		self.db_set("purchase_entry", entry)
		return entry
