"""The two gateways with their answers simulated: a payment is recorded only when the gateway's verify
says it was paid for the transaction's amount, never on what the customer's return URL says."""

from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon

SEND = "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request"


@tagged("post_install", "-at_install")
class TestIranianGateways(PaymentCommon):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.rial = cls.env.ref("base.IRR")
		cls.rial.active = True
		cls.zarinpal = cls._prepare_provider("zarinpal", update_values={"veron_merchant": "zarin-test"})
		cls.zibal = cls._prepare_provider("zibal", update_values={"veron_merchant": False})

	def _transaction(self, provider):
		return self._create_transaction("redirect", provider_id=provider.id, currency_id=self.rial.id,
			amount=1250000, payment_method_id=self.env.ref("veron_payment_iran.payment_method_shetab").id)

	def test_zarinpal_paid(self):
		tx = self._transaction(self.zarinpal)
		answers = [{"data": {"code": 100, "authority": "A0001"}}, {"data": {"code": 100, "ref_id": 987654, "card_pan": "6037**1234"}}]
		with patch(SEND, side_effect=answers) as send:
			values = tx._get_specific_rendering_values({})
			self.assertEqual(values["api_url"], "https://sandbox.zarinpal.com/pg/StartPay/A0001")
			self.assertEqual(send.call_args.kwargs["json"]["amount"], 1250000)
			tx._process("zarinpal", tx._veron_verify({"ref": tx.reference, "Authority": "A0001", "Status": "OK"}))
			self.assertEqual(send.call_args.kwargs["json"], {"merchant_id": "zarin-test", "amount": 1250000, "authority": "A0001"})
		self.assertEqual(tx.state, "done")
		self.assertEqual(tx.provider_reference, "987654")

	def test_zarinpal_refused_by_verify(self):
		tx = self._transaction(self.zarinpal)
		answers = [{"data": {"code": 100, "authority": "A0002"}}, {"data": {"code": -51}, "errors": {"message": "Session is not valid"}}]
		with patch(SEND, side_effect=answers):
			tx._get_specific_rendering_values({})
			tx._process("zarinpal", tx._veron_verify({"ref": tx.reference, "Authority": "A0002", "Status": "OK"}))
		self.assertEqual(tx.state, "error")

	def test_zarinpal_cancelled_and_foreign_authority(self):
		tx = self._transaction(self.zarinpal)
		with patch(SEND, side_effect=[{"data": {"code": 100, "authority": "A0003"}}]) as send:
			tx._get_specific_rendering_values({})
			with self.assertRaises(Exception):
				tx._veron_verify({"ref": tx.reference, "Authority": "SOMEONE-ELSES", "Status": "OK"})
			tx._process("zarinpal", tx._veron_verify({"ref": tx.reference, "Authority": "A0003", "Status": "NOK"}))
			self.assertEqual(send.call_count, 1)  # no verify for a cancelled payment
		self.assertEqual(tx.state, "cancel")

	def test_zibal_test_merchant_and_amount_check(self):
		tx = self._transaction(self.zibal)
		answers = [{"result": 100, "trackId": 15966442}, {"result": 100, "amount": 1000, "refNumber": 1, "orderId": tx.reference}]
		with patch(SEND, side_effect=answers) as send:
			values = tx._get_specific_rendering_values({})
			self.assertEqual(send.call_args.kwargs["json"]["merchant"], "zibal")
			self.assertEqual(values["api_url"], "https://gateway.zibal.ir/start/15966442")
			# Paid, but not the transaction's amount: not recorded as paid
			tx._process("zibal", tx._veron_verify({"ref": tx.reference, "trackId": "15966442", "success": "1"}))
		self.assertEqual(tx.state, "error")

	def test_zibal_paid(self):
		tx = self._transaction(self.zibal)
		answers = [{"result": 100, "trackId": 777}, {"result": 100, "amount": 1250000, "refNumber": 5551, "orderId": tx.reference}]
		with patch(SEND, side_effect=answers):
			tx._get_specific_rendering_values({})
			tx._process("zibal", tx._veron_verify({"ref": tx.reference, "trackId": "777", "success": "1"}))
		self.assertEqual(tx.state, "done")
		self.assertEqual(tx.provider_reference, "5551")
