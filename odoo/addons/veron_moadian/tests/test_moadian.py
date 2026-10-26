import base64
import datetime
import json
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.veron_moadian.tools import jose, payload
from odoo.addons.veron_moadian.tools.tax_id import generate_tax_id, is_valid_verhoeff, parse_tax_id, verhoeff_digit


def key_and_certificate():
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
	now = datetime.datetime.now(datetime.timezone.utc)
	certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
		.serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
	key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
	return key, key_pem, certificate.public_bytes(serialization.Encoding.PEM).decode()


@tagged("post_install", "-at_install")
class TestTaxIdAndPacket(TransactionCase):
	def test_verhoeff_and_tax_id(self):
		self.assertEqual(verhoeff_digit("236"), 3)
		self.assertTrue(is_valid_verhoeff("2363"))
		# The tax number of the open-source SDKs' tests
		self.assertTrue(parse_tax_id("A111220E1B9155CB1F18C7")["valid"])
		self.assertFalse(parse_tax_id("A111220E1B9155CB1F18C8")["valid"])
		tax_id = generate_tax_id("a11122", datetime.date(2026, 10, 12), 113)
		self.assertEqual(len(tax_id), 22)
		parts = parse_tax_id(tax_id)
		self.assertTrue(parts["valid"])
		self.assertEqual((parts["date"], parts["serial"]), (datetime.date(2026, 10, 12), 113))

	def test_payload(self):
		invoice = {
			"currency": "IRR", "invoice_date": datetime.date(2026, 10, 12), "amount_total": 2200000, "amount_residual": 2090000,
			"lines": [
				{"row": 1, "name": "کابل", "quantity": 10, "price_unit": 100000, "discount": 10, "subtotal": 900000, "total": 990000,
				 "vat_rate": 10, "sstid": "2720000000001", "unit": "1627"},
				{"row": 2, "name": "نصب", "quantity": 1, "price_unit": 1100000, "discount": 0, "subtotal": 1100000, "total": 1210000,
				 "vat_rate": 10, "sstid": "2330000000002", "unit": "1627"},
			],
		}
		data, problems = payload.build(invoice, {"economic_code": "14000000001"}, {"national_id": "۰۰۱۲۳۴۵۶۷۸"},
			{"memory_id": "A11122", "tax_id": "X", "serial": 26})
		self.assertEqual(problems, [])
		cable = data["body"][0]
		self.assertEqual((cable["fee"], cable["prdis"], cable["dis"], cable["adis"], cable["vam"]), (100000, 1000000, 100000, 900000, 90000))
		header = data["header"]
		self.assertEqual((header["tadis"], header["tvam"], header["tbill"]), (2000000, 200000, 2200000))
		self.assertEqual((header["inno"], header["inty"], header["tob"], header["bid"]), ("000000001A", 1, 1, "0012345678"))
		self.assertEqual((header["setm"], header["insp"], header["cap"]), (3, 2090000, 110000))
		# Without the buyer, the seller and the codes
		invoice["lines"][0]["sstid"] = None
		data, problems = payload.build(invoice, {}, {}, {})
		self.assertEqual(data["header"]["inty"], 2)
		self.assertEqual({code for code, _values in problems}, {"memory", "seller", "sstid"})

	def test_sign_and_encrypt(self):
		_key, key_pem, certificate_pem = key_and_certificate()
		server_key, _server_pem, _server_certificate = key_and_certificate()
		jws = jose.sign({"header": {"taxid": "X"}}, key_pem, certificate_pem)
		self.assertEqual(jose.verify(jws, certificate_pem), {"header": {"taxid": "X"}})
		header = json.loads(jose.b64url_decode(jws.split(".")[0]))
		self.assertEqual((header["alg"], header["crit"]), ("RS256", ["sigT"]))
		jwe = jose.encrypt(jws, server_key.public_key(), "key-1")
		self.assertEqual(json.loads(jose.b64url_decode(jwe.split(".")[0])), {"alg": "RSA-OAEP-256", "enc": "A256GCM", "kid": "key-1"})
		self.assertEqual(jose.decrypt(jwe, server_key), jws)


class FakeResponse:
	def __init__(self, body, status=200):
		self.body, self.status_code, self.text = body, status, json.dumps(body)

	def json(self):
		return self.body


@tagged("post_install", "-at_install")
class TestMoadianInvoice(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env.user.group_ids |= cls.env.ref("account.group_account_manager")
		cls.company = cls.env.company
		cls.key, cls.key_pem, cls.certificate_pem = key_and_certificate()
		cls.server_key = key_and_certificate()[0]
		cls.company.write({
			"vat": "14000000001", "veron_moadian_memory_id": "a11122",
			"veron_moadian_private_key": cls.key_pem, "veron_moadian_certificate": cls.certificate_pem,
		})
		cls.tax = cls.env["account.tax"].create({"name": "VAT 10", "amount": 10, "amount_type": "percent", "type_tax_use": "sale"})
		cls.product = cls.env["product.product"].create({"name": "کابل", "veron_sstid": "2720000000001", "list_price": 100000})
		cls.customer = cls.env["res.partner"].create({"name": "خریدار", "veron_national_id": "0012345679", "zip": "1234567890"})

	def invoice(self):
		move = self.env["account.move"].create({
			"move_type": "out_invoice", "partner_id": self.customer.id, "invoice_date": "2026-10-12",
			"invoice_line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 10, "price_unit": 100000, "discount": 10,
				"tax_ids": [(6, 0, self.tax.ids)]})],
		})
		move.action_post()
		return move

	def test_identifiers(self):
		with self.assertRaises(ValidationError):
			self.env["res.partner"].create({"name": "x", "veron_national_id": "0012345678"})
		with self.assertRaises(ValidationError):
			self.product.veron_sstid = "123"

	def test_prepare(self):
		move = self.invoice()
		move.action_veron_moadian_prepare()
		self.assertEqual(move.veron_moadian_state, "prepared", move.veron_moadian_problems)
		self.assertTrue(parse_tax_id(move.veron_tax_id)["valid"])
		self.assertTrue(move.veron_tax_id.startswith("A11122"))
		data = json.loads(move.veron_moadian_payload)
		self.assertEqual((data["header"]["tadis"], data["header"]["tvam"], data["header"]["tbill"]), (900000, 90000, 990000))
		self.assertEqual(data["body"][0]["mu"], "1627")
		# A product without its id: listed, no tax number
		self.product.veron_sstid = False
		other = self.invoice()
		other.action_veron_moadian_prepare()
		self.assertEqual(other.veron_moadian_state, "problems")
		self.assertFalse(other.veron_tax_id)

	def test_send_and_result(self):
		move = self.invoice()
		move.action_veron_moadian_prepare()
		with self.assertRaises(UserError):
			move.action_veron_moadian_send()
		self.company.veron_moadian_active = True
		server_public = base64.b64encode(self.server_key.public_key().public_bytes(
			serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
		received = []

		def fake(method, url, headers=None, timeout=None, params=None, json=None):
			path = url.rsplit("/", 1)[1]
			if path == "nonce":
				return FakeResponse({"nonce": "n-1"})
			if path == "server-information":
				return FakeResponse({"publicKeys": [{"id": "k-1", "key": server_public}]})
			token = jose.verify(headers["authorization"].split(" ", 1)[1], self.certificate_pem)
			self.assertEqual(token, {"nonce": "n-1", "clientId": "A11122"})
			if path == "invoice":
				packet = json[0]
				received.append(jose.verify(jose.decrypt(packet["payload"], self.server_key), self.certificate_pem))
				return FakeResponse({"result": [{"uid": packet["header"]["requestTraceId"], "referenceNumber": "ref-1"}]})
			self.assertEqual(params, {"referenceIds": "ref-1"})
			return FakeResponse([{"referenceNumber": "ref-1", "status": "SUCCESS", "data": {"confirmationReferenceId": "c-1"}}])

		with patch("odoo.addons.veron_moadian.tools.client.requests.request", side_effect=fake):
			move.action_veron_moadian_send()
			self.assertEqual((move.veron_moadian_state, move.veron_moadian_reference), ("sent", "ref-1"))
			self.assertEqual(received[0]["header"]["taxid"], move.veron_tax_id)
			with self.assertRaises(UserError):
				move.button_draft()
			move.action_veron_moadian_inquire()
		self.assertEqual(move.veron_moadian_state, "accepted")

	def test_rejected(self):
		move = self.invoice()
		move.action_veron_moadian_prepare()
		move.write({"veron_moadian_state": "sent", "veron_moadian_reference": "ref-2"})
		self.company.veron_moadian_active = True
		answer = [{"referenceNumber": "ref-2", "status": "FAILED", "data": {"error": [{"code": "0100", "message": "شناسه کالا نامعتبر"}]}}]
		with patch("odoo.addons.veron_moadian.tools.client.Client.inquire", return_value=answer):
			move.action_veron_moadian_inquire()
		self.assertEqual(move.veron_moadian_state, "rejected")
		self.assertIn("0100", move.veron_moadian_result)
		move.action_veron_moadian_retry()
		self.assertEqual(move.veron_moadian_state, "prepared")
