import frappe
from frappe.tests import IntegrationTestCase

from iran_erp.help import content, get_guide
from iran_erp.help.guides import DOCTYPES

TEXT_KEYS = ("about", "after", "example")
LIST_KEYS = ("before", "steps", "mistakes", "tips", "related")


class TestHelpGuides(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def check_shape(self, name, guide):
		for key in TEXT_KEYS:
			if key in guide:
				self.assertIsInstance(guide[key], str, f"{name}: {key}")
		for key in LIST_KEYS:
			if key in guide:
				self.assertIsInstance(guide[key], list, f"{name}: {key}")
				self.assertTrue(all(isinstance(item, str) and item for item in guide[key]), f"{name}: {key}")
		for key in ("fields", "columns"):
			if key in guide:
				self.assertIsInstance(guide[key], dict, f"{name}: {key}")

	def test_guides_name_real_fields(self):
		"""A field the guide explains is a field of the form, so a click on it can find it."""
		for doctype, guide in {**DOCTYPES, **content.GUIDES}.items():
			self.check_shape(doctype, guide)
			if not frappe.db.exists("DocType", doctype):
				continue
			meta = frappe.get_meta(doctype)
			for fieldname in guide.get("fields") or {}:
				self.assertTrue(meta.get_field(fieldname), f"{doctype}: no field {fieldname}")

	def test_related_pages_exist(self):
		guides = {**content.GUIDES, **content.REPORTS, **content.WORKSPACES}
		for name, guide in guides.items():
			for doctype in guide.get("related") or []:
				self.assertTrue(frappe.db.exists("DocType", doctype), f"{name}: no DocType {doctype}")

	def test_report_and_workspace_guides(self):
		for report, guide in content.REPORTS.items():
			self.check_shape(report, guide)
		for workspace, guide in content.WORKSPACES.items():
			self.check_shape(workspace, guide)

	def test_full_guide_is_served(self):
		guide = get_guide("doctype", "Sales Invoice")
		self.assertTrue(guide.get("about"))
		self.assertTrue(guide.get("steps"))
		# The short guide's fields stay, with the complete guide's laid over them
		self.assertIn("customer", guide["fields"])
		if "Sales Invoice" in content.GUIDES:
			self.assertTrue(guide.get("mistakes"))
