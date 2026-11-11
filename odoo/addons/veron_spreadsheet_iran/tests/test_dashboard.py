import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSampleDashboard(HttpCase):
	def test_sample_has_its_module_and_currency(self):
		dashboards = self.env["spreadsheet.dashboard"].search([("sample_dashboard_file_path", "!=", False)])
		dashboard = dashboards.filtered(lambda d: d._dashboard_is_empty())[:1]
		if not dashboard:
			self.skipTest("No dashboard shows its sample here")
		self.authenticate("admin", "admin")
		self.opener.headers["X-Odoo-Database"] = self.env.cr.dbname
		data = json.loads(self.url_open(f"/spreadsheet/dashboard/data/{dashboard.id}").content)
		if not data.get("is_sample"):
			self.skipTest("The dashboard has data, so no sample is shown")
		self.assertEqual(data["translation_namespace"], dashboard._get_dashboard_translation_namespace())
		self.assertEqual(data["default_currency"]["code"], self.env.company.currency_id.name)
		self.assertIn("locale", data["snapshot"]["settings"])
		self.assertNotIn("[$$]", json.dumps(data["snapshot"]), "no dollars in a sample")
