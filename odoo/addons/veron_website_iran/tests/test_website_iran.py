import re
from unittest.mock import MagicMock, patch

from odoo.tests import HttpCase, new_test_user, tagged

from ..models.otp import mobile

SENT = []


def capture(self, *args, **kwargs):
	SENT.extend(self.mapped("body"))


@tagged("post_install", "-at_install")
class TestWebsiteIran(HttpCase):
	def setUp(self):
		super().setUp()
		SENT.clear()
		# The test server has several databases: this one is named
		self.opener.headers["X-Odoo-Database"] = self.env.cr.dbname
		# A session of its own, as a visitor's browser keeps
		self.authenticate(None, None)
		self.website = self.env["website"].get_current_website()
		self.env["ir.config_parameter"].sudo().set_param("auth_signup.invitation_scope", "b2c")
		if "auth_signup_uninvited" in self.website._fields:
			self.website.auth_signup_uninvited = "b2c"

	def login_steps(self, number, code=None):
		page = self.url_open("/web/login/mobile")
		token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
		data = {"csrf_token": token, "mobile": number}
		if code is not None:
			data["code"] = code
		return self.url_open("/web/login/mobile", data=data)

	def code(self):
		return re.search(r"(\d{6})", SENT[-1]).group(1)

	def test_numbers(self):
		self.assertEqual([mobile(n) for n in ("+98 912 123 4567", "۰۹۱۲۱۲۳۴۵۶۷", "9121234567", "021-1234")],
			["09121234567", "09121234567", "09121234567", None])

	@patch("odoo.addons.sms.models.sms_sms.SmsSms._send", capture)
	def test_sign_up_and_log_in(self):
		self.login_steps("09121110000")
		self.assertTrue(SENT, "a code is sent")
		code = self.code()
		Code = self.env["veron.login.code"].sudo()
		self.assertNotIn(code, Code.search([("mobile", "=", "09121110000")]).code_hash, "only its hash is kept")
		wrong = self.login_steps("09121110000", "000000" if code != "000000" else "111111")
		self.assertIn("alert-danger", wrong.text)
		answer = self.login_steps("09121110000", code)
		user = self.env["res.users"].search([("login", "=", "09121110000")])
		self.assertTrue(user and user._is_portal(), "a new number becomes a portal user: " + answer.text[-1500:])
		session = self.url_open("/web/session/get_session_info", data="{}", headers={"Content-Type": "application/json"})
		self.assertEqual(session.json()["result"]["uid"], user.id)
		again = self.login_steps("09121110000", code)
		self.assertIn("alert-danger", again.text, "a code works once")

	@patch("odoo.addons.sms.models.sms_sms.SmsSms._send", capture)
	def test_limits_and_internal_users(self):
		self.login_steps("09121110001")
		self.login_steps("09121110001")
		self.assertEqual(len(SENT), 1, "one code a minute for a number")
		for _try in range(5):
			self.login_steps("09121110001", "999999")
		code = self.code()
		late = self.login_steps("09121110001", code)
		self.assertIn("alert-danger", late.text, "five wrong tries end the code")
		internal = new_test_user(self.env, "veron_internal", groups="base.group_user")
		internal.partner_id.phone = "09121110002"
		self.login_steps("09121110002")
		refused = self.login_steps("09121110002", self.code())
		self.assertIn("alert-danger", refused.text, "an internal user uses the password")

	def test_neshan_and_podcast(self):
		self.assertEqual(self.url_open("/veron/neshan/static?lat=35.7&lng=51.4").status_code, 404, "no key, no map")
		self.website.sudo().veron_neshan_key = "service.key"
		image = MagicMock(status_code=200, content=b"\x89PNG", headers={"Content-Type": "image/png"})
		with patch("requests.get", return_value=image) as get:
			answer = self.url_open("/veron/neshan/static?lat=35.7&lng=51.4&zoom=14")
		self.assertEqual((answer.status_code, answer.content), (200, b"\x89PNG"))
		self.assertEqual(get.call_args.kwargs["params"]["center"], "35.7,51.4")
		self.assertNotIn("service.key", self.url_open("/veron/neshan/map?lat=35.7&lng=51.4").text, "the key stays on the server")
		self.env["veron.podcast.episode"].create({"name": "قسمت اول", "audio_url": "https://cdn.example/1.mp3",
			"is_published": True, "description": "<p>درباره حسابداری</p>"})
		self.env["veron.podcast.episode"].create({"name": "پیش‌نویس", "audio_url": "https://cdn.example/2.mp3"})
		page = self.url_open("/podcast")
		self.assertIn("قسمت اول", page.text)
		self.assertNotIn("پیش‌نویس", page.text, "not published, not shown")
		rss = self.url_open("/podcast/rss.xml")
		self.assertIn("https://cdn.example/1.mp3", rss.text)

	def test_blocks_offered(self):
		snippets = self.env["ir.qweb"]._render("veron_website_iran.s_aparat", {})
		self.assertIn("aparat.com/video/video/embed", str(snippets))
		from lxml import etree

		arch = etree.tostring(self.env.ref("website.snippets")._get_combined_arch(), encoding="unicode")
		self.assertIn("veron_website_iran.s_neshan", arch)
