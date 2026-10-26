"""Posts to messaging channels through each platform's bot API; Bale's is Telegram's own, Eitaayar's
takes the same parameters as a form."""

import base64
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 30
CAPTION_LIMIT = 1024
API = {
	"telegram": "https://api.telegram.org/bot{token}/",
	"bale": "https://tapi.bale.ai/bot{token}/",
	"eitaa": "https://eitaayar.ir/api/{token}/",
}


class SocialAccount(models.Model):
	_name = "veron.social.account"
	_description = "Social Channel"

	name = fields.Char(required=True)
	platform = fields.Selection([("bale", "Bale"), ("eitaa", "Eitaa"), ("telegram", "Telegram")], required=True, default="bale")
	token = fields.Char("Bot Token", groups="base.group_system", copy=False,
		help="Bale and Telegram: the token the platform's BotFather gave the bot. Eitaa: the Eitaayar token.")
	chat_id = fields.Char("Channel", required=True, help="The channel's @username, or its numeric id")
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

	def _send(self, text, image=None, image_name="image.jpg"):
		"""Send a post; the platform's message id, or a UserError with its error"""
		self.ensure_one()
		account = self.sudo()
		if not account.token:
			raise UserError(_("The channel %s has no token.", self.name))
		base = API[self.platform].format(token=account.token)
		try:
			if image:
				files_key = "file" if self.platform == "eitaa" else "photo"
				method = "sendFile" if self.platform == "eitaa" else "sendPhoto"
				caption = text if len(text or "") <= CAPTION_LIMIT else ""
				answer = self._call(base + method, data={"chat_id": self.chat_id, "caption": caption},
					files={files_key: (image_name, base64.b64decode(image))})
				if text and not caption:
					answer = self._call(base + "sendMessage", data={"chat_id": self.chat_id, "text": text})
			else:
				answer = self._call(base + "sendMessage", data={"chat_id": self.chat_id, "text": text})
		except requests.exceptions.RequestException as error:
			_logger.warning("%s not reached: %s", self.platform, error)
			raise UserError(_("%(platform)s could not be reached: %(error)s", platform=self.platform, error=error)) from error
		return str((answer.get("result") or {}).get("message_id") or "")

	@api.model
	def _call(self, url, data, files=None):
		response = requests.post(url, data=data, files=files, timeout=TIMEOUT)
		try:
			answer = response.json()
		except ValueError:
			answer = {"ok": False, "description": response.text[:200]}
		if not answer.get("ok"):
			raise UserError(answer.get("description") or _("The platform refused the post (HTTP %s).", response.status_code))
		return answer

	def action_test(self):
		self.ensure_one()
		self._send(_("ERP-VERON: this channel is connected."))
		return {
			"type": "ir.actions.client",
			"tag": "display_notification",
			"params": {"message": _("The test message was sent to %s.", self.name), "type": "success"},
		}


class SocialPost(models.Model):
	_name = "veron.social.post"
	_description = "Social Post"
	_inherit = ["mail.thread"]
	_order = "id desc"

	name = fields.Char(compute="_compute_name", store=True)
	message = fields.Text(required=True)
	image = fields.Image("Picture", max_width=2048, max_height=2048)
	account_ids = fields.Many2many("veron.social.account", string="Channels", required=True)
	scheduled_date = fields.Datetime("Post On", help="Empty: posted when «Post Now» is pressed")
	state = fields.Selection([("draft", "Draft"), ("scheduled", "Scheduled"), ("posted", "Posted"),
		("partial", "Partly Posted"), ("failed", "Failed")], default="draft", required=True, tracking=True, copy=False)
	line_ids = fields.One2many("veron.social.post.line", "post_id", "Results", readonly=True, copy=False)
	posted_date = fields.Datetime(readonly=True, copy=False)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

	@api.depends("message")
	def _compute_name(self):
		for post in self:
			text = (post.message or "").strip().splitlines()
			post.name = (text[0][:60] if text else "") or _("Post")

	def action_post_now(self):
		for post in self:
			post._post()
		return True

	def action_schedule(self):
		for post in self:
			if not post.scheduled_date:
				raise UserError(_("Set the date and time of the post first."))
		self.write({"state": "scheduled"})

	def action_draft(self):
		self.write({"state": "draft"})

	def _post(self):
		"""Each channel at its turn; one that fails does not stop the others"""
		self.ensure_one()
		if self.state in ("posted",):
			return
		done = self.line_ids.filtered(lambda l: l.state == "posted").account_id
		lines = []
		for account in self.account_ids - done:
			try:
				external = account._send(self.message, self.image)
				lines.append({"account_id": account.id, "state": "posted", "external_id": external})
			except UserError as error:
				lines.append({"account_id": account.id, "state": "failed", "error": str(error)})
		self.line_ids.filtered(lambda l: l.state == "failed" and l.account_id.id in [v["account_id"] for v in lines]).unlink()
		self.write({"line_ids": [(0, 0, vals) for vals in lines]})
		failed = self.line_ids.filtered(lambda l: l.state == "failed")
		posted = self.line_ids.filtered(lambda l: l.state == "posted")
		self.write({
			"state": "failed" if not posted else "partial" if failed else "posted",
			"posted_date": fields.Datetime.now() if posted else False,
		})

	@api.model
	def _cron_post_scheduled(self):
		for post in self.search([("state", "=", "scheduled"), ("scheduled_date", "<=", fields.Datetime.now())]):
			post._post()


class SocialPostLine(models.Model):
	_name = "veron.social.post.line"
	_description = "Social Post Result"

	post_id = fields.Many2one("veron.social.post", required=True, ondelete="cascade")
	account_id = fields.Many2one("veron.social.account", "Channel", required=True)
	platform = fields.Selection(related="account_id.platform")
	state = fields.Selection([("posted", "Posted"), ("failed", "Failed")], required=True)
	external_id = fields.Char("Message Id")
	error = fields.Char()
