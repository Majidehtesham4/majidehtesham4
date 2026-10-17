# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

"""A car's file at the dealership, from the day it comes in to the day it leaves.

Every car gets a code (CAR-00001). The file holds what the car is (model, colour, plate, chassis),
where it is (branch, parking, spot), whose it is, its body condition marked on a diagram, the
expert's scores for its technical and interior condition, the documents handed over, every
preparation, repair or paperwork cost, and its sale. «Everything That Happened» logs each change
with who made it and when.

A car is owned by the business, by an investor (bought with their money, for them), or by a
customer who left it to be sold on their behalf. A car of the business is its stock: the
purchase and every cost are entered as the car's value («موجودی خودرو»), and that value is the
cost of the sale. Of another owner's car, the business keeps its commission; costs it paid are
taken from what the owner receives unless set otherwise.

The branch is the branch of whoever registers the car (the «شعبه» of their user); only a System
Manager can move a car to another branch, and the move is logged.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, getdate, now_datetime, nowdate

from iran_erp.business import account, journal, party_account, require_cash_account
from iran_erp.iran_dealership.printing import car_money
from iran_erp.utils.jalali import format_jalali

ADMIN_ROLE = "System Manager"
DOCUMENTS = (
	"doc_ownership",
	"doc_card",
	"doc_insurance",
	"doc_body_insurance",
	"doc_spare_key",
	"doc_warranty",
	"doc_fines_clear",
	"doc_tax_clear",
	"doc_technical_check",
)
# Changes worth a line in the car's file: field, how its value is shown
WATCHED = (
	("status", lambda v: _(v) if v else ""),
	("branch", str),
	("parking", str),
	("parking_spot", str),
	("ownership", lambda v: _(v) if v else ""),
	("asking_price", lambda v: car_money(v) if v else ""),
	("mileage", str),
)


def user_branch(user=None):
	"""The branch a user works at, as set on their user."""
	return frappe.db.get_value("User", user or frappe.session.user, "iran_branch")


def is_admin():
	return ADMIN_ROLE in frappe.get_roles()


class IranVehicle(Document):
	def onload(self):
		self.set_onload("is_admin", is_admin())
		self.set_onload("user_branch", user_branch())

	def before_insert(self):
		if not self.inspection:
			self.fill_inspection()

	def validate(self):
		model = frappe.db.get_value("Iran Car Model", self.car_model, "title") if self.car_model else ""
		self.title = " ".join(str(part) for part in (model, self.year, self.color) if part)
		if self.plate:
			self.title += f" - {self.plate}"
		self.set_branch()
		self.check_owner()
		require_cash_account(self.paid_from, self.company)
		for row in self.costs:
			require_cash_account(row.paid_from, self.company)
		self.set_totals()
		self.body_summary = self.summarize_body()
		if self.exit_date:
			self.days_in_lot = date_diff(self.exit_date, self.entry_date)
		self.log_changes()

	def set_branch(self):
		mine = user_branch()
		if self.is_new():
			if not self.branch or (mine and not is_admin()):
				self.branch = mine or self.branch
			return
		before = self.get_doc_before_save()
		if before and before.branch != self.branch and not is_admin():
			frappe.throw(_("Only an administrator can move a car to another branch"))

	def check_owner(self):
		if self.ownership != "Business" and self.purchase_entry:
			frappe.throw(_("A car whose purchase is in the business's books cannot belong to someone else"))
		if self.ownership == "Investor" and self.investment_contract and not self.investor:
			self.investor = frappe.db.get_value(
				"Iran Investment Contract", self.investment_contract, "investor"
			)
		if self.ownership == "Customer" and self.owner_customer:
			national_id = frappe.db.get_value("Customer", self.owner_customer, "iran_national_id")
			if national_id and not self.owner_national_id:
				self.owner_national_id = national_id

	def set_totals(self):
		totals = {"Preparation": 0, "Repair": 0}
		other = 0
		for row in self.costs:
			if row.status != "Done":
				continue
			if row.category in totals:
				totals[row.category] += flt(row.amount)
			else:
				other += flt(row.amount)
		self.preparation_total = totals["Preparation"]
		self.repair_total = totals["Repair"]
		self.paperwork_total = other
		costs = self.preparation_total + self.repair_total + self.paperwork_total
		self.total_cost = costs + (flt(self.purchase_price) if self.ownership == "Business" else 0)
		if self.sold_price:
			self.profit = self.sale_profit()

	def sale_profit(self):
		price = flt(self.sold_price)
		if self.ownership == "Business":
			return price - flt(self.total_cost)
		commission = price * flt(self.commission_rate) / 100
		costs = flt(self.total_cost)
		return flt(commission - (0 if cint(self.charge_costs_to_owner) else costs), 0)

	def summarize_body(self):
		if not self.body_marks:
			return _("Body without marks")
		# «کاپوت: رنگ دارد، خط و خش؛ گلگیر جلو راست: تصادفی», part by part in the order recorded
		parts = {}
		for row in self.body_marks:
			parts.setdefault(row.body_part, []).append(row.condition)
		return "؛ ".join(f"{part}: {'، '.join(conditions)}" for part, conditions in parts.items())

	def fill_inspection(self):
		for item in frappe.get_all(
			"Iran Inspection Item",
			filters={"disabled": 0},
			fields=["name", "section", "measure"],
			order_by="section asc, sort_order asc, name asc",
		):
			self.append("inspection", {"item": item.name, "section": item.section, "measure": item.measure})

	# ------------------------------------------------------------ the car's file

	def add_log(self, event, details=""):
		self.append(
			"log",
			{"date": now_datetime(), "event": event, "details": details, "user": frappe.session.user},
		)

	def log_changes(self):
		if self.is_new():
			place = " / ".join(str(v) for v in (self.branch, self.parking, self.parking_spot) if v)
			self.add_log(_("Car came in"), _("Entry date {0}; {1}").format(format_jalali(self.entry_date), place))
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field, show in WATCHED:
			old, new = before.get(field), self.get(field)
			if (old or "") != (new or "") and not (isinstance(old, float | int) and flt(old) == flt(new)):
				label = _(self.meta.get_label(field))
				self.add_log(_("{0} changed").format(label), f"{show(old) or '—'} ← {show(new) or '—'}")
		old_costs = {row.name for row in before.costs}
		for row in self.costs:
			if row.name not in old_costs:
				self.add_log(
					_("Service: {0}").format(row.service),
					f"{car_money(row.amount)} — {_(row.status)}",
				)
		if len(before.body_marks) != len(self.body_marks):
			self.add_log(_("Body condition recorded"), self.summarize_body())
		ticked = [d for d in DOCUMENTS if self.get(d) and not before.get(d)]
		if ticked:
			self.add_log(_("Documents received"), "، ".join(_(self.meta.get_label(d)) for d in ticked))

	# ------------------------------------------------------------ the books

	def on_update(self):
		changed = False
		if self.ownership == "Business" and not self.purchase_entry and flt(self.purchase_price):
			if self.seller or self.paid_from:
				self.record_purchase(quiet=True)
				changed = True
		for row in self.costs:
			if (
				row.status == "Done"
				and not row.journal_entry
				and flt(row.amount) > 0
				and (row.paid_from or row.vendor)
			):
				row.db_set("journal_entry", self.cost_entry(row))
				changed = True
		if changed:
			self.notify_update()

	def cost_entry(self, row):
		"""A cost in the books: on the car's value, on its owner, or an expense of the business."""
		if self.ownership == "Business":
			debit = {"account": account(self.company, "vehicle_stock")}
		elif cint(self.charge_costs_to_owner):
			debit = self.owner_party_row()
		else:
			debit = {"account": account(self.company, "preparation_expense")}
		if row.paid_from:
			credit = {"account": row.paid_from}
		else:
			credit = {
				"account": party_account("Supplier", row.vendor, self.company),
				"party_type": "Supplier",
				"party": row.vendor,
			}
		return journal(
			self.company,
			row.date or nowdate(),
			[{**debit, "debit": row.amount}, {**credit, "credit": row.amount}],
			_("{0} of car {1} ({2})").format(row.service, self.title, self.name),
			branch=self.branch,
		)

	def owner_party_row(self):
		if self.ownership == "Investor":
			supplier = frappe.db.get_value("Iran Investor", self.investor, "supplier")
			return {
				"account": party_account("Supplier", supplier, self.company),
				"party_type": "Supplier",
				"party": supplier,
			}
		return {
			"account": party_account("Customer", self.owner_customer, self.company),
			"party_type": "Customer",
			"party": self.owner_customer,
		}

	def on_trash(self):
		if self.purchase_entry or any(row.journal_entry for row in self.costs) or self.sale_contract:
			frappe.throw(_("This car is in the books; it cannot be deleted"))

	@frappe.whitelist()
	def record_purchase(self, quiet=False):
		"""The purchase in the books: the car's value against the seller or the account paid from."""
		if not quiet:
			self.check_permission("write")
		if self.purchase_entry:
			frappe.throw(_("The purchase is already recorded"))
		if self.ownership != "Business":
			frappe.throw(_("Only a car the business owns is recorded as its stock"))
		if flt(self.purchase_price) <= 0:
			frappe.throw(_("Enter the purchase price first"))
		if self.seller:
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
			self.purchase_date or self.entry_date or nowdate(),
			[
				{"account": account(self.company, "vehicle_stock"), "debit": self.purchase_price},
				{**credit, "credit": self.purchase_price},
			],
			_("Purchase of car {0} ({1})").format(self.title, self.name),
			branch=self.branch,
		)
		self.db_set("purchase_entry", entry)
		self.append_log_now(_("Purchase recorded in the books"), entry)
		return entry

	def append_log_now(self, event, details=""):
		self.add_log(event, details)
		row = self.log[-1]
		row.parent, row.parenttype, row.parentfield = self.name, self.doctype, "log"
		row.db_insert()

	# ------------------------------------------------------------ reserve, sell, leave

	@frappe.whitelist()
	def reserve(self, customer: str | None = None, note: str | None = None):
		self.check_permission("write")
		if self.status not in ("In Preparation", "Ready for Sale"):
			frappe.throw(_("Only a car in the lot can be reserved"))
		self.status = "Reserved"
		self.save()
		name = frappe.db.get_value("Customer", customer, "customer_name") if customer else ""
		self.append_log_now(_("Reserved"), " — ".join(v for v in (name, note) if v))

	@frappe.whitelist()
	def unreserve(self):
		self.check_permission("write")
		if self.status != "Reserved":
			frappe.throw(_("The car is not reserved"))
		self.status = "Ready for Sale"
		self.save()

	@frappe.whitelist()
	def record_exit(self, date: str | None = None, delivered_to: str | None = None):
		"""The car leaves the lot after its sale."""
		self.check_permission("write")
		if self.status != "Sold":
			frappe.throw(_("A car leaves the lot after it is sold"))
		self.status = "Exited"
		self.exit_date = date or nowdate()
		self.delivered_to = delivered_to
		self.save()
		self.append_log_now(_("Car left the lot"), delivered_to or "")

	def mark_sold(self, contract, sold=True):
		"""Called by the sale contract."""
		self.status = "Sold" if sold else "Ready for Sale"
		self.sale_contract = contract.name if sold else None
		self.sold_price = contract.sale_price if sold else 0
		self.profit = self.sale_profit() if sold else 0
		self.flags.ignore_permissions = True
		self.save()
		self.append_log_now(
			_("Sold") if sold else _("Sale cancelled"),
			f"{contract.name} — {contract.customer_name or ''} — "
			f"{car_money(contract.sale_price)}",
		)


@frappe.whitelist()
def get_body_options():
	"""The body parts and conditions to choose from, for the body diagram."""
	return {
		"parts": frappe.get_all(
			"Iran Body Part",
			filters={"disabled": 0},
			fields=["name", "diagram_key"],
			order_by="sort_order asc, name asc",
		),
		"conditions": frappe.get_all(
			"Iran Body Condition",
			filters={"disabled": 0},
			fields=["name", "color_code", "severity"],
			order_by="modified asc",
		),
	}


@frappe.whitelist()
def get_inspection_items():
	return frappe.get_all(
		"Iran Inspection Item",
		filters={"disabled": 0},
		fields=["name", "section", "measure"],
		order_by="section asc, sort_order asc, name asc",
	)


def days_in_lot(entry_date, exit_date=None):
	return date_diff(getdate(exit_date or nowdate()), entry_date)
