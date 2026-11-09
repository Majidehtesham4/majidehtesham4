import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsappWebhook(http.Controller):
	@http.route("/veron/whatsapp/webhook", type="http", auth="public", methods=["GET"], csrf=False)
	def verify(self, **params):
		"""Meta's check of the webhook: the verify token of one of the numbers"""
		token = params.get("hub.verify_token")
		if params.get("hub.mode") == "subscribe" and token and request.env["veron.whatsapp.account"].sudo().search_count(
				[("verify_token", "=", token)]):
			return request.make_response(params.get("hub.challenge", ""), headers=[("Content-Type", "text/plain")])
		return request.make_response("", status=403)

	@http.route("/veron/whatsapp/webhook", type="http", auth="public", methods=["POST"], csrf=False)
	def receive(self):
		body = request.httprequest.get_data()
		signature = request.httprequest.headers.get("X-Hub-Signature-256")
		try:
			payload = json.loads(body or b"{}")
		except ValueError:
			return request.make_response("", status=400)
		ids = {(c.get("value") or {}).get("metadata", {}).get("phone_number_id") for e in payload.get("entry") or []
			for c in e.get("changes") or []}
		Account = request.env["veron.whatsapp.account"].sudo()
		for account in Account.search([("phone_number_id", "in", [i for i in ids if i])]):
			# Only what Meta signed with the app's secret is taken
			if not account._check_signature(body, signature):
				_logger.warning("WhatsApp webhook with a wrong signature for %s", account.name)
				return request.make_response("", status=403)
			request.env["veron.whatsapp.message"].sudo().with_company(account.company_id)._receive(account, payload)
		return request.make_response("ok")
