import base64
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

POST = "odoo.addons.veron_social.models.social.requests.post"
PNG = base64.b64encode(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d4a1e10000000049454e44ae426082"))


def answer(ok=True, description=None, message_id=7):
	response = MagicMock()
	response.json.return_value = {"ok": True, "result": {"message_id": message_id}} if ok else {"ok": False, "description": description}
	response.status_code = 200 if ok else 400
	return response


@tagged("post_install", "-at_install")
class TestSocial(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		Account = cls.env["veron.social.account"]
		cls.bale = Account.create({"name": "کانال بله", "platform": "bale", "chat_id": "@shop", "token": "BALE-TOKEN"})
		cls.eitaa = Account.create({"name": "کانال ایتا", "platform": "eitaa", "chat_id": "shop", "token": "EITAA-TOKEN"})
		cls.telegram = Account.create({"name": "تلگرام", "platform": "telegram", "chat_id": "@shop", "token": "TG"})

	def test_text_to_bale_and_eitaa(self):
		post = self.env["veron.social.post"].create({"message": "تخفیف ویژه‌ی یلدا", "account_ids": [(6, 0, (self.bale | self.eitaa).ids)]})
		with patch(POST, return_value=answer()) as send:
			post.action_post_now()
		urls = sorted(call.args[0] for call in send.call_args_list)
		self.assertEqual(urls, ["https://eitaayar.ir/api/EITAA-TOKEN/sendMessage", "https://tapi.bale.ai/botBALE-TOKEN/sendMessage"])
		self.assertEqual(send.call_args.kwargs["data"]["text"], "تخفیف ویژه‌ی یلدا")
		self.assertEqual(post.state, "posted")
		self.assertEqual(post.name, "تخفیف ویژه‌ی یلدا")

	def test_picture_and_a_failing_channel(self):
		post = self.env["veron.social.post"].create({
			"message": "محصول جدید", "image": PNG, "account_ids": [(6, 0, (self.bale | self.telegram).ids)]})
		def reply(url, **kwargs):
			return answer(False, "Unauthorized") if "telegram" in url else answer()
		with patch(POST, side_effect=reply) as send:
			post.action_post_now()
		bale_call = next(c for c in send.call_args_list if "bale" in c.args[0])
		self.assertTrue(bale_call.args[0].endswith("/sendPhoto"))
		self.assertEqual(bale_call.kwargs["data"]["caption"], "محصول جدید")
		self.assertIn("photo", bale_call.kwargs["files"])
		self.assertEqual(post.state, "partial")
		failed = post.line_ids.filtered(lambda l: l.state == "failed")
		self.assertEqual(failed.account_id, self.telegram)
		self.assertEqual(failed.error, "Unauthorized")
		# Again: only the channel that failed is tried
		with patch(POST, return_value=answer()) as send:
			post.action_post_now()
		self.assertEqual(send.call_count, 1)
		self.assertEqual(post.state, "posted")

	def test_long_text_with_picture_goes_after_it(self):
		long_text = "ا" * 2000
		with patch(POST, return_value=answer()) as send:
			self.eitaa._send(long_text, PNG)
		self.assertEqual([c.args[0].rsplit("/", 1)[1] for c in send.call_args_list], ["sendFile", "sendMessage"])

	def test_schedule(self):
		post = self.env["veron.social.post"].create({"message": "x", "account_ids": [(6, 0, self.bale.ids)], "scheduled_date": "2020-01-01 10:00:00"})
		post.action_schedule()
		self.assertEqual(post.state, "scheduled")
		with patch(POST, return_value=answer()):
			self.env["veron.social.post"]._cron_post_scheduled()
		self.assertEqual(post.state, "posted")
