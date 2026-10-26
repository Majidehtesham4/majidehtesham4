import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class IranianGatewayController(http.Controller):
	"""The customer back from the gateway's page. What comes in the URL is never trusted: the payment
	is asked again from the gateway itself (_veron_verify) before it is recorded."""

	@http.route(
		["/payment/zarinpal/return", "/payment/zibal/return"],
		type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False,
	)
	def veron_return(self, **data):
		code = request.httprequest.path.split("/")[2]
		_logger.info("Back from %s with:\n%s", code, pprint.pformat(data))
		tx_sudo = request.env["payment.transaction"].sudo()._search_by_reference(code, data)
		# A payment already settled is not verified again
		if tx_sudo and tx_sudo.state in ("draft", "pending"):
			try:
				tx_sudo._process(code, tx_sudo._veron_verify(data))
			except ValidationError as error:
				_logger.warning("Payment %s not processed: %s", tx_sudo.reference, error)
				tx_sudo._set_error(str(error))
		return request.redirect("/payment/status")
