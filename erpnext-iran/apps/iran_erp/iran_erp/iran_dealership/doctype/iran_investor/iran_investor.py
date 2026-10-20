# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

"""Someone who puts money in the business for a share of profit.

In the books an investor is a party of the «سرمایه‌گذاران» supplier group: what the business owes
them (their money and the profit earned on it) is in «حساب سرمایه‌گذاران» under their name. The
supplier is made with the investor.

An investor can be given a login: they then see their own account only («حساب من»: contracts,
profit earned to date, cheques), unless more is given to them.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from iran_erp.business import investor_group


class IranInvestor(Document):
	def validate(self):
		from iran_erp.utils.national_id import normalize_digits

		for field in ("mobile", "national_id", "iban"):
			if self.get(field):
				self.set(field, normalize_digits(self.get(field)).strip().replace(" ", ""))

	def before_insert(self):
		if not self.supplier:
			supplier = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": self.full_name,
					"supplier_group": investor_group(frappe.defaults.get_user_default("Company")),
					"supplier_type": "Individual",
					"mobile_no": self.mobile,
				}
			)
			supplier.flags.ignore_permissions = True
			# Another party (or investor) may already have this name
			from frappe.model.naming import append_number_if_name_exists

			supplier.insert(set_name=append_number_if_name_exists("Supplier", self.full_name))
			self.supplier = supplier.name

	def on_update(self):
		if (
			self.supplier
			and frappe.db.get_value("Supplier", self.supplier, "supplier_name") != self.full_name
		):
			frappe.db.set_value("Supplier", self.supplier, "supplier_name", self.full_name)

	@frappe.whitelist()
	def create_login(self, username: str, password: str, email: str | None = None):
		"""A login that opens on the investor's own account and shows nothing else (or a new
		username and password for the login they have)."""
		from iran_erp.users import investor_login

		return investor_login(self.name, username, password, email)
