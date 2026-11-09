from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestFonts(HttpCase):
	def test_font_files_served(self):
		for name in ("Vazirmatn-Regular.ttf", "Sahel-Bold.woff2", "Samim.ttf"):
			response = self.url_open(f"/veron_fonts_iran/static/fonts/{name}")
			self.assertEqual(response.status_code, 200, name)

	def test_report_in_the_company_font(self):
		self.env.company.veron_report_font = "Shabnam"
		html = self.env["ir.qweb"]._render("web.report_layout", {"res_company": self.env.company, "title": "x",
			"html_data": {}, "web_base_url": ""})
		self.assertIn('"Shabnam"', str(html))
