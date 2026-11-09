"""The banks' gateways with their answers simulated: recorded only when the bank verifies and settles the
payment; reversed when it is verified and not settled; never on what the customer's return says"""

import base64
import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon

from ..models.payment_bank import sign


def soap(value):
	response = MagicMock()
	response.text = f"<soap:Envelope><soap:Body><ns2:x><return>{value}</return></ns2:x></soap:Body></soap:Envelope>"
	response.status_code = 200
	return response


def http(status=200, body=None, text=None):
	response = MagicMock()
	response.status_code = status
	response.content = b"x"
	response.json.return_value = body or {}
	response.text = text if text is not None else json.dumps(body or {})
	return response


@tagged("post_install", "-at_install")
class TestBankGateways(PaymentCommon):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.rial = cls.env.ref("base.IRR")
		cls.rial.active = True
		cls.key = base64.b64encode(b"0123456789abcdefABCDEFGH").decode()
		cls.mellat = cls._prepare_provider("mellat", update_values={"veron_terminal": "123", "veron_username": "u",
			"veron_password": "p"})
		cls.sadad = cls._prepare_provider("sadad", update_values={"veron_merchant": "M1", "veron_terminal": "T1",
			"veron_key": cls.key})
		cls.asan = cls._prepare_provider("asanpardakht", update_values={"veron_terminal": "7001", "veron_username": "u",
			"veron_password": "p"})

	def transaction(self, provider, reference=None):
		values = {"reference": reference} if reference else {}
		return self._create_transaction("redirect", provider_id=provider.id, currency_id=self.rial.id, amount=1250000,
			payment_method_id=self.env.ref("veron_payment_iran.payment_method_shetab").id, **values)

	def test_mellat_paid_and_settled(self):
		tx = self.transaction(self.mellat)
		with patch("requests.post", side_effect=[soap("0,AB12CD"), soap("0"), soap("0")]) as post:
			values = tx._get_specific_rendering_values({})
			self.assertEqual((values["api_url"], values["method"], values["inputs"]["RefId"]),
				("https://bpm.shaparak.ir/pgwchannel/startpay.mellat", "post", "AB12CD"))
			self.assertIn(b"<amount>1250000</amount>", post.call_args.kwargs["data"])
			tx._process("mellat", tx._veron_verify({"ref": tx.reference, "RefId": "AB12CD", "ResCode": "0",
				"SaleOrderId": str(tx.id), "SaleReferenceId": "998877"}))
			self.assertIn(b"bpSettleRequest", post.call_args.kwargs["data"])
		self.assertEqual((tx.state, tx.provider_reference), ("done", "998877"))

	def test_mellat_not_settled_is_reversed(self):
		tx = self.transaction(self.mellat)
		with patch("requests.post", side_effect=[soap("0,R1"), soap("0"), soap("17"), soap("0")]) as post:
			tx._get_specific_rendering_values({})
			tx._process("mellat", tx._veron_verify({"ref": tx.reference, "RefId": "R1", "ResCode": "0", "SaleReferenceId": "5"}))
			self.assertIn(b"bpReversalRequest", post.call_args.kwargs["data"])
		self.assertEqual(tx.state, "error")
		other = self.transaction(self.mellat, "veron-mellat-2")
		with patch("requests.post", side_effect=[soap("0,R2")]):
			other._get_specific_rendering_values({})
		with self.assertRaises(ValidationError):
			other._veron_verify({"RefId": "SOMEONE-ELSE", "ResCode": "0", "SaleReferenceId": "1"})
		other._process("mellat", other._veron_verify({"ref": other.reference, "RefId": "R2", "ResCode": "17"}))
		self.assertEqual(other.state, "cancel")

	def test_sadad_signed_and_verified(self):
		tx = self.transaction(self.sadad)
		answers = [http(body={"ResCode": "0", "Token": "TK1"}), http(body={"ResCode": "0", "Amount": 1250000,
			"RetrivalRefNo": "445566", "OrderId": tx.id})]
		with patch("requests.post", side_effect=answers) as post:
			values = tx._get_specific_rendering_values({})
			sent = post.call_args.kwargs["json"]
			self.assertEqual(sent["SignData"], sign(self.key, f"T1;{tx.id};1250000"))
			self.assertEqual(values["api_url"], "https://sadad.shaparak.ir/Purchase?token=TK1")
			tx._process("sadad", tx._veron_verify({"ref": tx.reference, "token": "TK1", "ResCode": "0"}))
			self.assertEqual(post.call_args.kwargs["json"]["SignData"], sign(self.key, "TK1"))
		self.assertEqual((tx.state, tx.provider_reference), ("done", "445566"))

	def test_sadad_other_amount_not_recorded(self):
		tx = self.transaction(self.sadad)
		answers = [http(body={"ResCode": "0", "Token": "TK2"}), http(body={"ResCode": "0", "Amount": 1000, "OrderId": tx.id})]
		with patch("requests.post", side_effect=answers):
			tx._get_specific_rendering_values({})
			tx._process("sadad", tx._veron_verify({"ref": tx.reference, "token": "TK2", "ResCode": "0"}))
		self.assertEqual(tx.state, "error")

	def test_asanpardakht_verified_and_settled(self):
		tx = self.transaction(self.asan)
		answers = [http(text='"TOKEN9"'), http(body={"refID": "TOKEN9", "amount": 1250000, "rrn": "12345",
			"payGateTranID": 77, "cardNumber": "6037**"}), http(), http()]
		with patch("requests.request", side_effect=answers) as request:
			values = tx._get_specific_rendering_values({})
			self.assertEqual((values["inputs"]["RefId"], values["method"]), ("TOKEN9", "post"))
			self.assertEqual(json.loads(request.call_args_list[0].kwargs["data"])["amountInRials"], 1250000)
			tx._process("asanpardakht", tx._veron_verify({"ref": tx.reference, "RefId": "TOKEN9"}))
			self.assertEqual([call.args[1].rsplit("/", 1)[-1] for call in request.call_args_list],
				["Token", "TranResult", "Verify", "Settlement"])
		self.assertEqual((tx.state, tx.provider_reference), ("done", "12345"))

	def test_asanpardakht_left_the_page(self):
		tx = self.transaction(self.asan)
		with patch("requests.request", side_effect=[http(text='"T"'), http(status=472)]):
			tx._get_specific_rendering_values({})
			tx._process("asanpardakht", tx._veron_verify({"ref": tx.reference}))
		self.assertEqual(tx.state, "cancel")
