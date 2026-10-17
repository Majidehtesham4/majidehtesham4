"""The showroom website: what a customer sees, the instalment calculator and their requests."""

from unittest import TestCase

import frappe

from iran_erp.accounts.chart import CHART_NAME
from iran_erp.business import apply_pack
from iran_erp.iran_dealership import showroom
from iran_erp.iran_dealership.doctype.iran_instalment_sale.iran_instalment_sale import calculate

COMPANY = "Dealership Test Co"
MILLION = 1_000_000


class TestShowroom(TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Company", COMPANY):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY,
					"abbr": "DTC",
					"default_currency": "IRR",
					"country": "Iran",
					"chart_of_accounts": CHART_NAME,
				}
			).insert()
		apply_pack("Car Dealership", COMPANY)
		settings = frappe.get_single("Iran Showroom Settings")
		settings.update(
			{
				"enabled": 1,
				"show_prices": 1,
				"price_unit": "Toman",
				"monthly_rate": 4,
				"months_options": "6، ۱۲",
				"min_down_percent": 30,
				"experts": [],
			}
		)
		settings.append("experts", {"full_name": "کارشناس آزمایشی", "user": "Administrator"})
		settings.save()
		frappe.clear_document_cache("Iran Showroom Settings", "Iran Showroom Settings")
		model = frappe.db.get_value("Iran Car Model", {"made_in": "Made in Iran"})
		cls.shown = cls.car(model, show_on_website=1, website_headline="<script>alert(1)</script>")
		cls.hidden = cls.car(model)

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()

	@classmethod
	def car(cls, model, **values):
		return frappe.get_doc(
			{
				"doctype": "Iran Vehicle",
				"car_model": model,
				"year": "1403",
				"company": COMPANY,
				"status": "Ready for Sale",
				"asking_price": 20_000 * MILLION,
				"minimum_price": 19_000 * MILLION,
				"purchase_price": 17_000 * MILLION,
				**values,
			}
		).insert()

	def test_only_published_cars_and_nothing_private(self):
		cars = {c["name"]: c for c in showroom.list_cars()["cars"]}
		self.assertIn(self.shown.name, cars)
		self.assertNotIn(self.hidden.name, cars)
		listed = cars[self.shown.name]
		# Toman, Persian digits; typed text escaped
		self.assertEqual(listed["price"], "۲٬۰۰۰٬۰۰۰٬۰۰۰ تومان")
		self.assertNotIn("<script>", listed["headline"])
		page = showroom.car_page(self.shown.name)
		text = frappe.as_json(page)
		for private in (
			"purchase_price",
			"minimum_price",
			"owner_customer",
			"investor",
			"17000000000",
			"19000000000",
		):
			self.assertNotIn(private, text)
		self.assertRaises(frappe.PageDoesNotExistError, showroom.car_page, self.hidden.name)

	def test_a_sold_car_leaves_the_website(self):
		frappe.db.set_value("Iran Vehicle", self.shown.name, "status", "Sold")
		try:
			self.assertRaises(frappe.PageDoesNotExistError, showroom.car_page, self.shown.name)
		finally:
			frappe.db.set_value("Iran Vehicle", self.shown.name, "status", "Ready for Sale")

	def test_calculator_matches_the_contract(self):
		price = 20_000 * MILLION
		plan = showroom.simulate(self.shown.name, 8_000 * MILLION, 12)
		contract = calculate(price, 8_000 * MILLION, 0, 4, 12)
		self.assertEqual(plan["monthly"], contract["rows"][0]["amount"])
		self.assertEqual(plan["interest"], contract["interest"])
		self.assertEqual(plan["total"], 8_000 * MILLION + contract["total"])
		# Below the lowest down payment, or months not offered
		self.assertRaises(frappe.ValidationError, showroom.simulate, self.shown.name, 1_000 * MILLION, 12)
		self.assertRaises(frappe.ValidationError, showroom.simulate, self.shown.name, 8_000 * MILLION, 7)

	def test_a_request_reaches_an_expert(self):
		result = showroom.send_inquiry(
			full_name="خریدار سایت",
			mobile="۰۹۱۲ ۳۴۵ ۶۷۸۹",
			kind="Instalment Plan",
			vehicle=self.shown.name,
			down_payment=8_000 * MILLION,
			months=6,
		)
		inquiry = frappe.get_doc("Iran Car Inquiry", result["name"])
		self.assertEqual(inquiry.mobile, "09123456789")
		self.assertEqual(inquiry.expert, "Administrator")
		self.assertEqual(inquiry.months, 6)
		self.assertTrue(inquiry.monthly_amount)
		self.assertTrue(
			frappe.db.exists(
				"ToDo",
				{"reference_type": "Iran Car Inquiry", "reference_name": inquiry.name, "status": "Open"},
			)
		)
		self.assertRaises(
			frappe.ValidationError,
			showroom.send_inquiry,
			full_name="خریدار",
			mobile="12345",
			vehicle=self.shown.name,
		)
		# A request can become a sale with its plan
		from iran_erp.iran_dealership.doctype.iran_car_inquiry.iran_car_inquiry import make_sale

		sale = make_sale(inquiry.name)
		self.assertEqual(sale["vehicle"], self.shown.name)
		self.assertEqual(sale["down_payment"], 8_000 * MILLION)
		self.assertEqual(frappe.db.get_value("Customer", sale["customer"], "mobile_no"), "09123456789")
