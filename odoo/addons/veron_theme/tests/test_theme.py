from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTheme(TransactionCase):
	def test_new_users_dark_and_home(self):
		user = self.env["res.users"].create({"name": "کاربر نمونه", "login": "theme_user@example.com",
			"group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
		self.assertTrue(user.res_users_settings_id, "made with the user")
		self.assertTrue(user.dark_mode, "dark unless the person chooses light")
		self.assertTrue(user.is_redirect_home, "the home screen of the apps first")
		user.dark_mode = False
		self.assertFalse(user.res_users_settings_id.dark_mode, "the person's choice is kept")
		user.action_id = self.env.ref("base.action_res_users").id
		self.assertFalse(user.is_redirect_home, "a home action of their own wins")

	def test_assets(self):
		"""The light and the dark bundles are made with their own colors, and both compile"""
		Bundle = self.env["ir.qweb"]._get_asset_bundle
		for name, own, other in [("web.assets_web", "primary_variables.scss", "primary_variables.dark.scss"),
				("web.assets_web_dark", "primary_variables.dark.scss", "primary_variables.scss")]:
			bundle = Bundle(name, css=True, js=False)
			urls = [f["url"] for f in bundle.files]
			self.assertIn("/veron_theme/static/src/scss/" + own, urls)
			self.assertNotIn("/veron_theme/static/src/scss/" + other, urls)
			self.assertIn("/veron_theme/static/src/scss/theme.scss", urls)
			bundle.css()
			self.assertFalse(bundle.css_errors, f"{name}: {bundle.css_errors}")


@tagged("post_install", "-at_install")
class TestLogin(HttpCase):
	def test_login_page(self):
		self.env.company.logo = False
		self.opener.headers["X-Odoo-Database"] = self.env.cr.dbname
		html = self.url_open("/web/login").text
		self.assertIn("o_veron_login_page", html)
		self.assertIn("veron-mark.svg", html, "ERP-VERON's mark while the company has no logo")
