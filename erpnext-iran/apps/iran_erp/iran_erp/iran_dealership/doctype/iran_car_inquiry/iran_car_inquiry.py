# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

"""A customer's request from the showroom website (or taken by phone): a call back, a test drive or
an instalment plan for a car. Each request goes to the next expert in turn, as a ToDo."""

import re

import frappe
from frappe import _
from frappe.model.document import Document

MOBILE = re.compile(r"^09\d{9}$")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normal_mobile(mobile: str) -> str:
	"""«۰۹۱۲ ۱۲۳ ۴۵۶۷», «+989121234567» → «09121234567»"""
	mobile = re.sub(r"[\s\-()]", "", (mobile or "").translate(DIGITS))
	if mobile.startswith("+98"):
		mobile = "0" + mobile[3:]
	elif mobile.startswith("0098"):
		mobile = "0" + mobile[4:]
	elif mobile.startswith("9") and len(mobile) == 10:
		mobile = "0" + mobile
	return mobile


class IranCarInquiry(Document):
	def validate(self):
		self.mobile = normal_mobile(self.mobile)
		if not MOBILE.match(self.mobile):
			frappe.throw(_("Enter a mobile number like 09121234567"))
		self.full_name = (self.full_name or "").strip()
		if self.vehicle and not self.branch:
			self.branch = frappe.db.get_value("Iran Vehicle", self.vehicle, "branch")
		if not self.expert:
			self.expert = next_expert(self.branch)

	def after_insert(self):
		if not self.expert:
			return
		# The guest who sends the request may not assign it; the request itself does
		from frappe.desk.form.assign_to import _add

		_add(
			{
				"assign_to": [self.expert],
				"doctype": self.doctype,
				"name": self.name,
				"description": _("{0}: {1} {2}").format(_(self.kind), self.full_name, self.car_title or ""),
			},
			ignore_permissions=True,
		)


def next_expert(branch: str | None = None) -> str | None:
	"""The expert (of the branch, if it has any) who was given a request longest ago."""
	experts = frappe.get_all(
		"Iran Showroom Expert",
		filters={"parent": "Iran Showroom Settings", "user": ("is", "set")},
		fields=["user", "branch"],
		order_by="idx asc",
	)
	if branch and any(e.branch == branch for e in experts):
		experts = [e for e in experts if e.branch == branch]
	if not experts:
		return None
	last = {
		row.expert: row.last
		for row in frappe.get_all(
			"Iran Car Inquiry",
			filters={"expert": ("in", [e.user for e in experts])},
			fields=["expert", {"MAX": "creation", "as": "last"}],
			group_by="expert",
		)
	}
	return min(experts, key=lambda e: (last.get(e.user) is not None, str(last.get(e.user) or "")))["user"]


@frappe.whitelist()
def make_sale(inquiry: str) -> dict:
	"""A new instalment sale for the request: its customer (found by mobile, or made), the car and
	the plan the customer chose on the website. Returned unsaved, for the expert to complete."""
	doc = frappe.get_doc("Iran Car Inquiry", inquiry)
	doc.check_permission("write")
	customer = frappe.db.get_value("Customer", {"mobile_no": doc.mobile}) or (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": doc.full_name,
				"customer_type": "Individual",
				"mobile_no": doc.mobile,
			}
		)
		.insert()
		.name
	)
	sale = frappe.new_doc("Iran Instalment Sale")
	sale.update(
		{
			"customer": customer,
			"vehicle": doc.vehicle,
			"branch": doc.branch,
			"sale_price": doc.sale_price
			or (frappe.db.get_value("Iran Vehicle", doc.vehicle, "asking_price") if doc.vehicle else 0),
			"down_payment": doc.down_payment,
			"months": doc.months,
			"monthly_rate": doc.monthly_rate,
			"remarks": _("From customer request {0}").format(doc.name),
		}
	)
	if doc.status in ("New", "Contacted"):
		doc.db_set("status", "Test Drive Booked" if doc.kind == "Test Drive" else "Contacted")
	return sale.as_dict()
