"""Odoo's SMS sent through an Iranian panel, one request per number, with each panel's answer turned
into Odoo's states: sent, or the reason it failed (credit, number, account, panel)."""

import logging
import re

import requests

from odoo import _

from odoo.addons.sms.tools.sms_api import SmsApiBase

_logger = logging.getLogger(__name__)

TIMEOUT = 15


def iranian_number(number):
	"""09121234567 from +989121234567, 00989121234567 or 989121234567; other countries as they are"""
	digits = re.sub(r"[^\d+]", "", number or "")
	for prefix in ("+98", "0098"):
		if digits.startswith(prefix):
			return "0" + digits[len(prefix):]
	if digits.startswith("98") and len(digits) == 12:
		return "0" + digits[2:]
	return digits


class SmsApiIran(SmsApiBase):
	PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
		"insufficient_credit": "sms_credit",
		"unregistered": "sms_acc",
	}

	def _get_sms_api_error_messages(self):
		return {
			"server_error": _("The SMS panel could not be reached or refused the message."),
			"insufficient_credit": _("The SMS panel has no credit left."),
			"unregistered": _("The SMS panel's key, username or line is not valid."),
			"wrong_number_format": _("The number is not valid for the SMS panel."),
		}

	def _send_sms_batch(self, messages, delivery_reports_url=False):
		company = (self.company or self.env.company).sudo()
		send = getattr(self, f"_send_{company.veron_sms_provider}")
		results = []
		with requests.Session() as session:
			for message in messages:
				for number in message.get("numbers") or []:
					try:
						state, reason = send(session, company, iranian_number(number["number"]), message.get("content") or "")
					except requests.exceptions.RequestException as error:
						_logger.warning("SMS panel %s not reached: %s", company.veron_sms_provider, error)
						state, reason = "server_error", str(error)
					results.append({"uuid": number["uuid"], "state": state, "failure_reason": reason})
		return results

	def _send_kavenegar(self, session, company, number, text):
		params = {"receptor": number, "message": text}
		if company.veron_sms_line:
			params["sender"] = company.veron_sms_line
		response = session.post(f"https://api.kavenegar.com/v1/{company.veron_sms_key}/sms/send.json", data=params, timeout=TIMEOUT)
		status = ((response.json() or {}).get("return") or {}) if response.content else {}
		code = status.get("status", response.status_code)
		if code == 200:
			return "sent", False
		# 418: no credit; 401, 403, 412: key or line; 411: number
		return {418: "insufficient_credit", 401: "unregistered", 403: "unregistered", 412: "unregistered",
				411: "wrong_number_format"}.get(code, "server_error"), status.get("message") or response.text[:200]

	def _send_smsir(self, session, company, number, text):
		response = session.post(
			"https://api.sms.ir/v1/send/bulk",
			json={"lineNumber": int(company.veron_sms_line or 0), "messageText": text, "mobiles": [number]},
			headers={"X-API-KEY": company.veron_sms_key or "", "Accept": "application/json"},
			timeout=TIMEOUT,
		)
		answer = response.json() if response.content else {}
		if answer.get("status") == 1:
			return "sent", False
		# 0, 10 and 11: key; 13 and 101: line; 102 and 103: credit
		return {0: "unregistered", 10: "unregistered", 11: "unregistered", 13: "unregistered", 101: "unregistered",
				102: "insufficient_credit", 103: "insufficient_credit"}.get(answer.get("status"), "server_error"), \
			answer.get("message") or response.text[:200]

	def _send_melipayamak(self, session, company, number, text):
		response = session.post(
			"https://rest.payamak-panel.com/api/SendSMS/SendSMS",
			data={"username": company.veron_sms_username or "", "password": company.veron_sms_key or "",
				  "to": number, "from": company.veron_sms_line or "", "text": text, "isFlash": "false"},
			timeout=TIMEOUT,
		)
		answer = response.json() if response.content else {}
		if answer.get("RetStatus") == 1:
			return "sent", False
		# 0: username or password; 2: credit; 3: daily limit; 4: volume; 5: line; 7: forbidden words
		return {0: "unregistered", 2: "insufficient_credit", 5: "unregistered"}.get(answer.get("RetStatus"), "server_error"), \
			answer.get("StrRetStatus") or response.text[:200]
