"""Deleting all data asks for the word first; the deletion itself is tried on a site of its own
(it commits), not in the test suite."""

from unittest import TestCase

import frappe

from iran_erp import reset_data


class TestResetData(TestCase):
	def test_asks_for_the_word(self):
		frappe.set_user("Administrator")
		self.assertRaises(frappe.ValidationError, reset_data.start, confirm="yes")
		self.assertRaises(frappe.ValidationError, reset_data.start, confirm="")

	def test_keeps_what_the_system_is_built_on(self):
		for doctype in (
			"Company",
			"Account",
			"Fiscal Year",
			"Warehouse",
			"Cost Center",
			"User",
			"Iran Car Model",
		):
			self.assertNotIn(doctype, reset_data.DOCTYPES)
		# Every listed doctype exists in this system, or is skipped
		for doctype in reset_data.DOCTYPES:
			if frappe.db.exists("DocType", doctype):
				self.assertFalse(frappe.get_meta(doctype).istable, doctype)
