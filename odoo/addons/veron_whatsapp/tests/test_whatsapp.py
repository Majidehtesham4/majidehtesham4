import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.whatsapp import number

POST = "odoo.addons.veron_whatsapp.models.whatsapp.requests.post"


def answer(status=200, body=None):
	response = MagicMock(status_code=status)
	response.json.return_value = body if body is not None else {"messages": [{"id": "wamid.1"}]}
	return response


class Common:
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.account = cls.env["veron.whatsapp.account"].create({"name": "فروش", "phone_number_id": "111",
			"token": "test-token", "app_secret": "test-secret", "verify_token": "verify-me"})
		cls.partner = cls.env["res.partner"].create({"name": "مشتری نمونه", "phone": "0912 123 4567"})
		cls.template = cls.env["veron.whatsapp.template"].create({"name": "greeting", "account_id": cls.account.id,
			"body": "سلام {{1}}", "value_fields": "name"})


@tagged("post_install", "-at_install")
class TestWhatsapp(Common, TransactionCase):
	def test_numbers(self):
		self.assertEqual(number("0912 123 4567"), "989121234567")
		self.assertEqual(number("۰۹۱۲۱۲۳۴۵۶۷"), "989121234567")
		self.assertEqual(number("+98 912 123 4567"), "989121234567")
		self.assertEqual(number("00447700900123"), "447700900123")

	def test_template_sent(self):
		with patch(POST, return_value=answer()) as post:
			action = self.env["veron.whatsapp.composer"].with_context(active_model="res.partner",
				active_ids=self.partner.ids).create({"account_id": self.account.id, "template_id": self.template.id}).action_send()
		payload = post.call_args.kwargs["json"]
		self.assertEqual(payload["to"], "989121234567")
		self.assertEqual(payload["template"]["components"][0]["parameters"][0]["text"], "مشتری نمونه")
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")
		self.assertEqual(action["params"]["type"], "success")
		message = self.env["veron.whatsapp.message"].search([("partner_id", "=", self.partner.id)])
		self.assertEqual((message.wa_id, message.body), ("wamid.1", "سلام مشتری نمونه"))
		self.assertIn("سلام مشتری نمونه", self.partner.message_ids[0].body)

	def test_free_text_only_in_the_window(self):
		Message = self.env["veron.whatsapp.message"]
		with patch(POST, return_value=answer()), self.assertRaises(UserError):
			Message._send(self.account, self.partner.phone, self.partner, text="سلام")
		Message.create({"account_id": self.account.id, "phone": "989121234567", "direction": "in", "state": "received"})
		with patch(POST, return_value=answer()) as post:
			Message._send(self.account, self.partner.phone, self.partner, text="سلام")
		self.assertEqual(post.call_args.kwargs["json"]["text"]["body"], "سلام")

	def test_refused(self):
		with patch(POST, return_value=answer(400, {"error": {"message": "Invalid parameter"}})), \
				self.assertRaisesRegex(UserError, "Invalid parameter"):
			self.env["veron.whatsapp.message"]._send(self.account, self.partner.phone, self.partner, template=self.template)

	def test_statuses_and_answers(self):
		with patch(POST, return_value=answer()):
			sent = self.env["veron.whatsapp.message"]._send(self.account, self.partner.phone, self.partner, template=self.template)
		Message = self.env["veron.whatsapp.message"]

		def status(state):
			return {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "111"},
				"statuses": [{"id": "wamid.1", "status": state}]}}]}]}

		Message._receive(self.account, status("read"))
		Message._receive(self.account, status("delivered"))
		self.assertEqual(sent.state, "read", "a late delivery does not take it back")
		incoming = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "111"},
			"contacts": [{"wa_id": "989121234567", "profile": {"name": "Moshtari"}}],
			"messages": [{"id": "wamid.in", "from": "989121234567", "type": "text", "text": {"body": "ممنون"}}]}}]}]}
		Message._receive(self.account, incoming)
		Message._receive(self.account, incoming)
		received = Message.search([("direction", "=", "in")])
		self.assertEqual(len(received), 1, "kept once")
		self.assertEqual(received.partner_id, self.partner, "found by the number however it was written")
		self.assertIn("ممنون", self.partner.message_ids[0].body)

	def test_add_to_menu(self):
		self.template.action_add_to_menu()
		self.template.action_add_to_menu()
		self.assertEqual(self.env["ir.actions.act_window"].search_count([("res_model", "=", "veron.whatsapp.composer"),
			("binding_model_id.model", "=", "res.partner")]), 1)


@tagged("post_install", "-at_install")
class TestWebhook(Common, HttpCase):
	def test_verify_and_signature(self):
		self.opener.headers["X-Odoo-Database"] = self.env.cr.dbname
		ok = self.url_open("/veron/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=42")
		self.assertEqual((ok.status_code, ok.text), (200, "42"))
		self.assertEqual(self.url_open("/veron/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=no&hub.challenge=4").status_code, 403)
		body = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "111"},
			"messages": [{"id": "wamid.web", "from": "989121234567", "type": "text", "text": {"body": "سلام"}}]}}]}]}).encode()
		wrong = self.url_open("/veron/whatsapp/webhook", data=body, headers={"X-Hub-Signature-256": "sha256=bad",
			"Content-Type": "application/json"})
		self.assertEqual(wrong.status_code, 403)
		signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
		good = self.url_open("/veron/whatsapp/webhook", data=body, headers={"X-Hub-Signature-256": signature,
			"Content-Type": "application/json"})
		self.assertEqual(good.status_code, 200)
		self.assertTrue(self.env["veron.whatsapp.message"].search_count([("wa_id", "=", "wamid.web")]))
