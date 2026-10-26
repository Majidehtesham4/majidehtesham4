from odoo import fields, models

from .. import const


class PaymentProvider(models.Model):
	_inherit = "payment.provider"

	code = fields.Selection(
		selection_add=[("zarinpal", "Zarinpal"), ("zibal", "Zibal")],
		ondelete={"zarinpal": "set default", "zibal": "set default"},
	)
	veron_merchant = fields.Char(
		string="Merchant Code",
		help="The merchant code the gateway gave for this website (Zarinpal's merchant ID, Zibal's merchant)",
		copy=False,
		groups="base.group_system",
	)

	def _get_supported_currencies(self):
		currencies = super()._get_supported_currencies()
		if self.code in ("zarinpal", "zibal"):
			currencies = currencies.filtered(lambda c: c.name in const.SUPPORTED_CURRENCIES)
		return currencies

	def _get_default_payment_method_codes(self):
		self.ensure_one()
		if self.code not in ("zarinpal", "zibal"):
			return super()._get_default_payment_method_codes()
		return const.DEFAULT_PAYMENT_METHOD_CODES

	def _veron_merchant(self):
		"""The merchant code; Zibal's test merchant in test mode when none is set"""
		self.ensure_one()
		if self.code == "zibal" and self.state == "test" and not self.veron_merchant:
			return const.ZIBAL_TEST_MERCHANT
		return self.veron_merchant

	def _build_request_url(self, endpoint, **kwargs):
		if self.code == "zarinpal":
			return const.ZARINPAL[self.state if self.state == "test" else "enabled"][0] + endpoint.strip("/")
		if self.code == "zibal":
			return const.ZIBAL_API + endpoint.strip("/")
		return super()._build_request_url(endpoint, **kwargs)

	def _build_request_headers(self, method, endpoint, payload, **kwargs):
		if self.code in ("zarinpal", "zibal"):
			return {"Accept": "application/json", "Content-Type": "application/json"}
		return super()._build_request_headers(method, endpoint, payload, **kwargs)

	def _parse_response_error(self, response):
		if self.code == "zarinpal":
			errors = response.json().get("errors") or {}
			return errors.get("message", "") if isinstance(errors, dict) else str(errors)
		if self.code == "zibal":
			return response.json().get("message", "")
		return super()._parse_response_error(response)

	def _veron_payment_page(self, reference):
		"""The gateway's page where the customer pays, for the gateway's reference of the payment"""
		self.ensure_one()
		if self.code == "zarinpal":
			return const.ZARINPAL[self.state if self.state == "test" else "enabled"][1] + reference
		return const.ZIBAL_START + reference
