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


# The answers after which the next panel of the hub is tried
RETRY = ("server_error", "insufficient_credit", "unregistered")


class Panel:
	"""The settings of one panel, from the company (its main panel) or from a backup panel"""

	def __init__(self, provider, key, username, line):
		self.veron_sms_provider, self.veron_sms_key = provider, key
		self.veron_sms_username, self.veron_sms_line = username, line

	@classmethod
	def of_company(cls, company):
		return cls(company.veron_sms_provider, company.veron_sms_key, company.veron_sms_username, company.veron_sms_line)

	@classmethod
	def of_record(cls, record):
		return cls(record.provider, record.key, record.username, record.line)


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
		# The company's panel first, then its backup panels in their order (the hub): a message the panel could not
		# take (not reached, no credit, its account) goes to the next; a wrong number does not
		panels = [Panel.of_company(company)] + [Panel.of_record(record) for record in company._veron_sms_backups()]
		results = []
		with requests.Session() as session:
			for message in messages:
				for number in message.get("numbers") or []:
					state, reason = "server_error", _("No SMS panel is set.")
					for panel in panels:
						state, reason = self._send_one(session, panel, iranian_number(number["number"]),
							message.get("content") or "")
						if state not in RETRY:
							break
					results.append({"uuid": number["uuid"], "state": state, "failure_reason": reason})
		return results

	def _send_one(self, session, panel, number, text):
		send = getattr(self, f"_send_{panel.veron_sms_provider}", None)
		if not send:
			return "server_error", _("Unknown SMS panel.")
		try:
			return send(session, panel, number, text)
		except (requests.exceptions.RequestException, ValueError) as error:
			_logger.warning("SMS panel %s not reached: %s", panel.veron_sms_provider, error)
			return "server_error", str(error)

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

	def _send_farapayamak(self, session, company, number, text):
		# Farapayamak's panel is the same web service as Melipayamak's (payamak-panel.com)
		return self._send_melipayamak(session, company, number, text)

	def _send_farazsms(self, session, company, number, text):
		# FarazSMS runs on IPPanel: its REST API with the key in the «apikey» header
		response = session.post(
			"https://api2.ippanel.com/api/v1/sms/send/webservice/single",
			json={"recipient": [number], "sender": company.veron_sms_line or "", "message": text},
			headers={"apikey": company.veron_sms_key or "", "Accept": "application/json"},
			timeout=TIMEOUT,
		)
		answer = response.json() if response.content else {}
		if response.status_code == 200 and str(answer.get("status", "")).upper() in ("OK", "SUCCESS"):
			return "sent", False
		# 401 and 403: key; 422: the number or line; the error says if it is the credit
		reason = str((answer.get("data") or {}).get("error") or answer.get("message") or response.text[:200])
		if "credit" in reason.lower() or "اعتبار" in reason:
			return "insufficient_credit", reason
		return {401: "unregistered", 403: "unregistered", 422: "wrong_number_format"}.get(response.status_code,
			"server_error"), reason

	def _send_ghasedak(self, session, company, number, text):
		params = {"message": text, "receptor": number}
		if company.veron_sms_line:
			params["linenumber"] = company.veron_sms_line
		response = session.post("https://api.ghasedak.me/v2/sms/send/simple", data=params,
			headers={"apikey": company.veron_sms_key or "", "Accept": "application/json"}, timeout=TIMEOUT)
		result = ((response.json() or {}).get("result") or {}) if response.content else {}
		code = result.get("code", response.status_code)
		if code == 200:
			return "sent", False
		# 401 and 403: key; 412 and 418: line; 407: credit; 411: number
		return {401: "unregistered", 403: "unregistered", 412: "unregistered", 418: "unregistered",
				407: "insufficient_credit", 411: "wrong_number_format"}.get(code, "server_error"), \
			result.get("message") or response.text[:200]
