"""A payment with an Iranian gateway: the gateway is asked for a payment, the customer pays on its page
and comes back to /payment/<gateway>/return. The payment is recorded only when the gateway itself,
asked server to server (verify), says it was paid, for this transaction's amount."""

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools import urls

from odoo.addons.payment.logging import get_payment_logger

from .. import const

_logger = get_payment_logger(__name__)

RETURN_URL = "/payment/%s/return"


class PaymentTransaction(models.Model):
	_inherit = "payment.transaction"

	def _veron_rial(self):
		"""The amount in whole rials, as the gateways take it"""
		return int(round(self.amount))

	def _get_specific_rendering_values(self, processing_values):
		if self.provider_code not in ("zarinpal", "zibal"):
			return super()._get_specific_rendering_values(processing_values)
		provider = self.provider_id
		callback = urls.urljoin(provider.get_base_url(), RETURN_URL % self.provider_code) + f"?ref={self.reference}"
		try:
			if self.provider_code == "zarinpal":
				payload = {
					"merchant_id": provider._veron_merchant(),
					"amount": self._veron_rial(),
					"currency": "IRR",
					"description": self.reference,
					"callback_url": callback,
					"metadata": {k: v for k, v in (("mobile", self.partner_phone), ("email", self.partner_email)) if v},
				}
				answer = self._send_api_request("POST", "request.json", json=payload)
				data = answer.get("data") or {}
				if data.get("code") != 100 or not data.get("authority"):
					raise ValidationError(_("Zarinpal refused the payment: %s", data.get("message") or answer.get("errors")))
				gateway_reference = data["authority"]
			else:
				payload = {
					"merchant": provider._veron_merchant(),
					"amount": self._veron_rial(),
					"callbackUrl": callback,
					"orderId": self.reference,
					"description": self.reference,
				}
				if self.partner_phone:
					payload["mobile"] = self.partner_phone
				answer = self._send_api_request("POST", "request", json=payload)
				if answer.get("result") != 100 or not answer.get("trackId"):
					raise ValidationError(_("Zibal refused the payment: %s", answer.get("message")))
				gateway_reference = str(answer["trackId"])
		except ValidationError as error:
			self._set_error(str(error))
			return {}
		# Kept to check that the customer comes back from this very payment
		self.provider_reference = gateway_reference
		return {"api_url": provider._veron_payment_page(gateway_reference)}

	def _veron_verify(self, returned):
		"""What the gateway answers about this payment, asked server to server, as payment data for
		_process. returned: the values of the customer's return from the gateway's page."""
		self.ensure_one()
		data = {"ref": self.reference}
		if self.provider_code == "zarinpal":
			if returned.get("Authority") != self.provider_reference:
				raise ValidationError(_("The payment returned does not belong to this transaction."))
			if returned.get("Status") != "OK":
				return {**data, "status": "canceled"}
			answer = self._send_api_request("POST", "verify.json", json={
				"merchant_id": self.provider_id._veron_merchant(),
				"amount": self._veron_rial(),
				"authority": self.provider_reference,
			})
			result = answer.get("data") or {}
			if result.get("code") in const.ZARINPAL_PAID:
				# Zarinpal verifies the amount sent with it: a payment of another amount is refused
				return {**data, "status": "paid", "amount": self._veron_rial(),
						"gateway_reference": str(result.get("ref_id") or ""), "card": result.get("card_pan")}
			return {**data, "status": "failed", "message": str(answer.get("errors") or result.get("message") or "")}
		if str(returned.get("trackId")) != self.provider_reference:
			raise ValidationError(_("The payment returned does not belong to this transaction."))
		if str(returned.get("success")) != "1":
			return {**data, "status": "canceled"}
		answer = self._send_api_request("POST", "verify", json={
			"merchant": self.provider_id._veron_merchant(),
			"trackId": int(self.provider_reference),
		})
		if answer.get("result") in const.ZIBAL_PAID and answer.get("orderId") in (None, self.reference):
			return {**data, "status": "paid", "amount": answer.get("amount"),
					"gateway_reference": str(answer.get("refNumber") or ""), "card": answer.get("cardNumber")}
		return {**data, "status": "failed", "message": answer.get("message", "")}

	@api.model
	def _extract_reference(self, provider_code, payment_data):
		if provider_code not in ("zarinpal", "zibal"):
			return super()._extract_reference(provider_code, payment_data)
		return payment_data.get("ref")

	def _extract_amount_data(self, payment_data):
		if self.provider_code not in ("zarinpal", "zibal"):
			return super()._extract_amount_data(payment_data)
		if payment_data.get("status") != "paid":
			return None  # nothing paid: no amount to check
		return {"amount": float(payment_data.get("amount") or 0), "currency_code": "IRR", "precision_digits": 0}

	def _apply_updates(self, payment_data):
		if self.provider_code not in ("zarinpal", "zibal"):
			return super()._apply_updates(payment_data)
		status = payment_data.get("status")
		if status == "paid":
			# The gateway's own tracking number, the one on the customer's bank receipt
			if payment_data.get("gateway_reference"):
				self.provider_reference = payment_data["gateway_reference"]
			self._set_done()
		elif status == "canceled":
			self._set_canceled(_("The customer did not pay on the gateway's page."))
		else:
			_logger.info("Payment %s not verified by the gateway: %s", self.reference, payment_data)
			self._set_error(_("The gateway did not confirm the payment: %s", payment_data.get("message") or status))
