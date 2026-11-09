"""The gateways of the banks: Behpardakht Mellat (SOAP), Sadad of Bank Melli (signed REST) and Asan Pardakht
(REST). As with the others, the customer's return is not trusted: the payment is verified with the bank, then
settled, before it is recorded; one verified and not settled is reversed when the bank allows it."""

import base64
import json
import re
from xml.sax.saxutils import escape

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import urls

from odoo.addons.payment.logging import get_payment_logger

from .. import const

_logger = get_payment_logger(__name__)
TIMEOUT = 30


def sign(key, text):
	"""Sadad's SignData: the text encrypted with the merchant's key, Triple DES in ECB with PKCS#7 padding"""
	from cryptography.hazmat.primitives import padding
	from cryptography.hazmat.primitives.ciphers import Cipher, modes

	try:
		from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
	except ImportError:  # older cryptography
		from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
	padder = padding.PKCS7(64).padder()
	data = padder.update(text.encode()) + padder.finalize()
	encryptor = Cipher(TripleDES(base64.b64decode(key)), modes.ECB()).encryptor()  # noqa: S305 - the bank's own scheme
	return base64.b64encode(encryptor.update(data) + encryptor.finalize()).decode()


class PaymentTransaction(models.Model):
	_inherit = "payment.transaction"

	def _veron_callback(self):
		return urls.urljoin(self.provider_id.get_base_url(), f"/payment/{self.provider_code}/return") + f"?ref={self.reference}"

	def _veron_order_id(self):
		"""The number of the payment the banks need (a long integer, unique for the terminal): the transaction's id"""
		return self.id

	# --- Behpardakht Mellat

	def _veron_mellat(self, method, **values):
		"""A call of Mellat's SOAP service; its answer, «0» or «0,RefId» when done, else the error code"""
		provider = self.provider_id.sudo()
		values = dict(terminalId=provider.veron_terminal, userName=provider.veron_username,
			userPassword=provider.veron_password, **values)
		body = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in values.items())
		envelope = (f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
			f'xmlns:int="{const.MELLAT_NAMESPACE}"><soapenv:Body><int:{method}>{body}</int:{method}>'
			"</soapenv:Body></soapenv:Envelope>")
		try:
			response = requests.post(const.MELLAT_API, data=envelope.encode(), timeout=TIMEOUT,
				headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""})
		except requests.exceptions.RequestException as error:
			raise ValidationError(_("Mellat's gateway could not be reached: %s", error)) from error
		found = re.search(r"<return>([^<]*)</return>", response.text or "")
		if not found:
			raise ValidationError(_("Mellat's gateway gave no answer (%s).", response.status_code))
		return found.group(1).strip()

	def _veron_request_mellat(self):
		now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
		answer = self._veron_mellat("bpPayRequest", orderId=self._veron_order_id(), amount=self._veron_rial(),
			localDate=now.strftime("%Y%m%d"), localTime=now.strftime("%H%M%S"), additionalData=self.reference,
			callBackUrl=self._veron_callback(), payerId=0)
		code, _sep, ref_id = answer.partition(",")
		if code != const.MELLAT_OK or not ref_id:
			raise ValidationError(_("Mellat refused the payment (code %s).", code))
		values = {"RefId": ref_id}
		if self.partner_phone:
			values["MobileNo"] = re.sub(r"\D", "", self.partner_phone)[-12:]
		return ref_id, const.MELLAT_START, "post", values

	def _veron_verify_mellat(self, returned):
		data = {"ref": self.reference}
		if returned.get("RefId") != self.provider_reference:
			raise ValidationError(_("The payment returned does not belong to this transaction."))
		if str(returned.get("ResCode")) != const.MELLAT_OK or not returned.get("SaleReferenceId"):
			return {**data, "status": "canceled"}
		ids = {"orderId": self._veron_order_id(), "saleOrderId": returned.get("SaleOrderId") or self._veron_order_id(),
			"saleReferenceId": returned.get("SaleReferenceId")}
		verified = self._veron_mellat("bpVerifyRequest", **ids)
		if verified not in (const.MELLAT_OK, const.MELLAT_VERIFIED):
			# Not verified: given back to the customer by the bank; asked to be sure
			self._veron_mellat("bpReversalRequest", **ids)
			return {**data, "status": "failed", "message": _("Mellat did not verify it (code %s).", verified)}
		settled = self._veron_mellat("bpSettleRequest", **ids)
		if settled not in (const.MELLAT_OK, const.MELLAT_SETTLED):
			self._veron_mellat("bpReversalRequest", **ids)
			return {**data, "status": "failed", "message": _("Mellat did not settle it (code %s).", settled)}
		# Mellat verifies the amount of the order it was asked for
		return {**data, "status": "paid", "amount": self._veron_rial(), "gateway_reference": str(returned["SaleReferenceId"]),
			"card": returned.get("CardHolderPan")}

	# --- Sadad of Bank Melli

	def _veron_sadad(self, url, payload):
		try:
			response = requests.post(url, json=payload, timeout=TIMEOUT, headers={"Accept": "application/json"})
			return response.json() if response.content else {}
		except (requests.exceptions.RequestException, ValueError) as error:
			raise ValidationError(_("Sadad's gateway could not be reached: %s", error)) from error

	def _veron_request_sadad(self):
		provider = self.provider_id.sudo()
		order, amount = self._veron_order_id(), self._veron_rial()
		now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
		answer = self._veron_sadad(const.SADAD_REQUEST, {
			"MerchantId": provider.veron_merchant, "TerminalId": provider.veron_terminal, "Amount": amount, "OrderId": order,
			"LocalDateTime": now.strftime("%m/%d/%Y %I:%M:%S %p"), "ReturnUrl": self._veron_callback(),
			"SignData": sign(provider.veron_key, f"{provider.veron_terminal};{order};{amount}"),
		})
		if str(answer.get("ResCode")) != "0" or not answer.get("Token"):
			raise ValidationError(_("Sadad refused the payment: %s", answer.get("Description") or answer.get("ResCode")))
		return answer["Token"], const.SADAD_START + answer["Token"], "get", {}

	def _veron_verify_sadad(self, returned):
		data = {"ref": self.reference}
		token = returned.get("token") or returned.get("Token")
		if token != self.provider_reference:
			raise ValidationError(_("The payment returned does not belong to this transaction."))
		if str(returned.get("ResCode")) != "0":
			return {**data, "status": "canceled"}
		answer = self._veron_sadad(const.SADAD_VERIFY, {"Token": token,
			"SignData": sign(self.provider_id.sudo().veron_key, token)})
		if str(answer.get("ResCode")) == "0" and str(answer.get("OrderId", self._veron_order_id())) == str(self._veron_order_id()):
			return {**data, "status": "paid", "amount": answer.get("Amount"),
				"gateway_reference": str(answer.get("RetrivalRefNo") or answer.get("SystemTraceNo") or "")}
		return {**data, "status": "failed", "message": answer.get("Description") or str(answer.get("ResCode"))}

	# --- Asan Pardakht

	def _veron_asan(self, method, endpoint, **kwargs):
		provider = self.provider_id.sudo()
		headers = {"usr": provider.veron_username or "", "pwd": provider.veron_password or "",
			"Content-Type": "application/json", "Accept": "application/json"}
		try:
			response = requests.request(method, const.ASAN_API + endpoint, headers=headers, timeout=TIMEOUT, **kwargs)
		except requests.exceptions.RequestException as error:
			raise ValidationError(_("Asan Pardakht could not be reached: %s", error)) from error
		return response

	def _veron_request_asanpardakht(self):
		provider = self.provider_id.sudo()
		now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
		response = self._veron_asan("POST", "Token", data=json.dumps({
			"serviceTypeId": 1, "merchantConfigurationId": int(provider.veron_terminal or 0),
			"localInvoiceId": self._veron_order_id(), "amountInRials": self._veron_rial(),
			"localDate": now.strftime("%Y%m%d %H%M%S"), "additionalData": self.reference,
			"callbackURL": self._veron_callback(), "paymentId": "0",
		}))
		token = response.text.strip().strip('"') if response.status_code == 200 else ""
		if not token:
			raise ValidationError(_("Asan Pardakht refused the payment (%s).", response.status_code))
		values = {"RefId": token}
		if self.partner_phone:
			values["mobileap"] = re.sub(r"\D", "", self.partner_phone)[-11:]
		return token, const.ASAN_START, "post", values

	def _veron_verify_asanpardakht(self, returned):
		data = {"ref": self.reference}
		provider = self.provider_id.sudo()
		config = int(provider.veron_terminal or 0)
		result = self._veron_asan("GET", "TranResult", params={"merchantConfigurationId": config,
			"localInvoiceId": self._veron_order_id()})
		if result.status_code != 200:
			# 472: no payment of this invoice; the customer left the page
			return {**data, "status": "canceled"}
		paid = result.json()
		if str(paid.get("refID") or returned.get("RefId") or "") not in ("", self.provider_reference):
			raise ValidationError(_("The payment returned does not belong to this transaction."))
		ids = json.dumps({"merchantConfigurationId": config, "payGateTranId": paid.get("payGateTranID")})
		if self._veron_asan("POST", "Verify", data=ids).status_code != 200:
			self._veron_asan("POST", "Reverse", data=ids)
			return {**data, "status": "failed", "message": _("Asan Pardakht did not verify it.")}
		if self._veron_asan("POST", "Settlement", data=ids).status_code != 200:
			self._veron_asan("POST", "Reverse", data=ids)
			return {**data, "status": "failed", "message": _("Asan Pardakht did not settle it.")}
		return {**data, "status": "paid", "amount": paid.get("amount"), "gateway_reference": str(paid.get("rrn") or ""),
			"card": paid.get("cardNumber")}

	# --- the common steps

	def _get_specific_rendering_values(self, processing_values):
		if self.provider_code not in const.BANKS:
			return super()._get_specific_rendering_values(processing_values)
		try:
			reference, url, method, inputs = getattr(self, f"_veron_request_{self.provider_code}")()
		except ValidationError as error:
			self._set_error(str(error))
			return {}
		self.provider_reference = reference
		return {"api_url": url, "method": method, "inputs": inputs}

	def _veron_verify(self, returned):
		if self.provider_code in const.BANKS:
			self.ensure_one()
			return getattr(self, f"_veron_verify_{self.provider_code}")(returned)
		return super()._veron_verify(returned)
