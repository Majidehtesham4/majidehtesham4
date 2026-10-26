"""Odoo's SMS through the Iranian panels, their answers simulated"""

from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from ..tools.sms_api import iranian_number

POST = "requests.Session.post"


def answer(json):
	response = MagicMock()
	response.json.return_value = json
	response.content = b"x"
	response.status_code = 200
	return response


@tagged("post_install", "-at_install")
class TestIranianSms(TransactionCase):
	def _sms(self, number="+98 912 123 4567"):
		return self.env["sms.sms"].create({"number": number, "body": "سلام، نوبت شما فردا ساعت ۱۰ است."})

	def test_numbers(self):
		self.assertEqual(iranian_number("+98 912 123 4567"), "09121234567")
		self.assertEqual(iranian_number("00989121234567"), "09121234567")
		self.assertEqual(iranian_number("989121234567"), "09121234567")
		self.assertEqual(iranian_number("09121234567"), "09121234567")

	def test_kavenegar_sent_and_no_credit(self):
		self.env.company.write({"veron_sms_provider": "kavenegar", "veron_sms_key": "KEY", "veron_sms_line": "10004346"})
		sms = self._sms()
		with patch(POST, return_value=answer({"return": {"status": 200, "message": "تایید شد"}})) as post:
			sms._send(unlink_sent=False)
		self.assertEqual(post.call_args.args[0], "https://api.kavenegar.com/v1/KEY/sms/send.json")
		self.assertEqual(post.call_args.kwargs["data"]["receptor"], "09121234567")
		self.assertEqual(post.call_args.kwargs["data"]["sender"], "10004346")
		self.assertEqual(sms.state, "pending")
		sms = self._sms()
		with patch(POST, return_value=answer({"return": {"status": 418, "message": "اعتبار کافی نیست"}})):
			sms._send(unlink_failed=False)
		self.assertEqual((sms.state, sms.failure_type), ("error", "sms_credit"))

	def test_smsir_and_melipayamak(self):
		self.env.company.write({"veron_sms_provider": "smsir", "veron_sms_key": "K", "veron_sms_line": "30007732"})
		sms = self._sms()
		with patch(POST, return_value=answer({"status": 1, "message": "موفق"})) as post:
			sms._send(unlink_sent=False)
		self.assertEqual(post.call_args.kwargs["json"], {"lineNumber": 30007732, "messageText": sms.body, "mobiles": ["09121234567"]})
		self.assertEqual(post.call_args.kwargs["headers"]["X-API-KEY"], "K")
		self.assertEqual(sms.state, "pending")
		self.env.company.write({"veron_sms_provider": "melipayamak", "veron_sms_username": "u", "veron_sms_key": "p", "veron_sms_line": "5000"})
		sms = self._sms()
		with patch(POST, return_value=answer({"Value": "0", "RetStatus": 0, "StrRetStatus": "InvalidUserPass"})):
			sms._send(unlink_failed=False)
		self.assertEqual((sms.state, sms.failure_type), ("error", "sms_acc"))

	def test_without_panel_odoo_service_stays(self):
		self.env.company.veron_sms_provider = False
		from odoo.addons.sms.tools.sms_api import SmsApi
		self.assertIs(self.env.company._get_sms_api_class(), SmsApi)
