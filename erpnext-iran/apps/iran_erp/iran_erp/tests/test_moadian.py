import datetime
import json

import frappe
from frappe.tests import UnitTestCase

from iran_erp.moadian.invoice import build_payload, buyer_type
from iran_erp.moadian.tax_id import generate_tax_id, is_valid_verhoeff, parse_tax_id, verhoeff_digit


class TestTaxId(UnitTestCase):
	def test_verhoeff(self):
		self.assertEqual(verhoeff_digit("236"), 3)
		self.assertTrue(is_valid_verhoeff("2363"))
		self.assertFalse(is_valid_verhoeff("2364"))

	def test_sample_from_the_published_sdks(self):
		# The tax number used in the open-source Moadian SDKs' tests
		parts = parse_tax_id("A111220E1B9155CB1F18C7")
		self.assertTrue(parts["valid"])
		self.assertEqual(parts["memory_id"], "A11122")
		self.assertFalse(parse_tax_id("A111220E1B9155CB1F18C8")["valid"])

	def test_generate(self):
		tax_id = generate_tax_id("a11122", datetime.date(2026, 10, 12), 113)
		self.assertEqual(len(tax_id), 22)
		self.assertTrue(tax_id.startswith("A11122" + f"{20738:05X}" + f"{113:010X}"))
		parts = parse_tax_id(tax_id)
		self.assertTrue(parts["valid"])
		self.assertEqual(parts["date"], datetime.date(2026, 10, 12))
		self.assertEqual(parts["serial"], 113)
		self.assertRaises(ValueError, generate_tax_id, "A1112", datetime.date(2026, 10, 12), 1)
		self.assertRaises(ValueError, generate_tax_id, "A11122", datetime.date(2026, 10, 12), 0)


def fake_invoice(**kwargs):
	item = frappe._dict
	return frappe._dict(
		{
			"currency": "IRR",
			"posting_date": "2026-10-12",
			"creation": "2026-10-12 10:00:00",
			"grand_total": 2_200_000,
			"rounded_total": 2_200_000,
			# Partly paid
			"outstanding_amount": 2_090_000,
			"is_return": 0,
			"taxes": [
				item(account_head="VAT", charge_type="On Net Total", rate=10, account_type="Tax"),
			],
			"items": [
				# 10 cables listed at 100,000, sold at 90,000
				item(
					idx=1,
					item_code="CABLE",
					item_name="کابل",
					qty=10,
					price_list_rate=100_000,
					rate=90_000,
					net_amount=900_000,
					uom="Nos",
				),
				item(
					idx=2,
					item_code="SERVICE",
					item_name="نصب",
					qty=1,
					price_list_rate=0,
					rate=1_100_000,
					net_amount=1_100_000,
					uom="Nos",
				),
				# Exempt through its item tax template
				item(
					idx=3,
					item_code="BOOK",
					item_name="کتاب",
					qty=1,
					price_list_rate=0,
					rate=0,
					net_amount=0,
					uom="Nos",
					item_tax_rate=json.dumps({"VAT": 0}),
				),
			],
			**kwargs,
		}
	)


SELLER = {"iran_economic_code": "14000000001"}
BUYER = {"iran_national_id": "0012345678"}
ITEMS = {"CABLE": "2720000000001", "SERVICE": "2330000000002", "BOOK": "2720000000003"}
UNITS = {"Nos": "1627"}


class TestPayload(UnitTestCase):
	def test_lines_and_totals(self):
		settings = {"memory_id": "A11122", "tax_id": "X", "serial": 26}
		payload, problems = build_payload(fake_invoice(), SELLER, BUYER, ITEMS, UNITS, settings)
		self.assertEqual(problems, [])
		cable, service, book = payload["body"]
		self.assertEqual(
			(cable["fee"], cable["prdis"], cable["dis"], cable["adis"]),
			(100_000, 1_000_000, 100_000, 900_000),
		)
		self.assertEqual((cable["vra"], cable["vam"], cable["tsstam"]), (10, 90_000, 990_000))
		self.assertEqual(service["vam"], 110_000)
		self.assertEqual((book["vra"], book["vam"]), (0, 0))

		header = payload["header"]
		self.assertEqual((header["tprdis"], header["tdis"], header["tadis"]), (2_100_000, 100_000, 2_000_000))
		self.assertEqual((header["tvam"], header["tbill"]), (200_000, 2_200_000))
		self.assertEqual(header["inno"], "000000001A")
		self.assertEqual((header["inty"], header["tob"], header["bid"]), (1, 1, "0012345678"))
		self.assertEqual((header["setm"], header["insp"], header["cap"]), (3, 2_090_000, 110_000))

	def test_problems_are_listed(self):
		invoice = fake_invoice(
			currency="USD", grand_total=2_200_000, rounded_total=2_200_000, outstanding_amount=0
		)
		payload, problems = build_payload(invoice, {}, {}, {"CABLE": "2720000000001"}, {}, {})
		self.assertEqual(payload["header"]["inty"], 2)
		self.assertEqual(payload["header"]["setm"], 1)
		text = " ".join(problems)
		for expected in ("USD", "memory", "economic", "SERVICE", "unit"):
			self.assertIn(expected.lower(), text.lower())

	def test_buyer_type(self):
		self.assertEqual(buyer_type("۰۰۱۲۳۴۵۶۷۸"), 1)
		self.assertEqual(buyer_type("10100000001"), 2)
		self.assertIsNone(buyer_type(""))
