import re

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.veron_core.models import jalali
from odoo.addons.veron_dealership.models.instalment import add_shamsi_months


class DealershipCase(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.model = cls.env.ref("veron_dealership.car_model_1")
		cls.customer = cls.env["res.partner"].create({"name": "خریدار"})
		cls.owner = cls.env["res.partner"].create({"name": "صاحب خودرو"})
		cls.garage = cls.env["res.partner"].create({"name": "صافکاری"})
		cls.Vehicle = cls.env["veron.vehicle"]

	def car(self, **values):
		return self.Vehicle.create({"model_id": self.model.id, "year": "1403", "mileage": 20000, **values})


@tagged("post_install", "-at_install")
class TestVehicle(DealershipCase):
	def test_lists_and_plate(self):
		self.assertGreaterEqual(self.env["veron.car.model"].search_count([]), 78)
		self.assertEqual(self.model.display_name, "ایران‌خودرو پژو ۲۰۶")
		car = self.car(plate_left="۱۲", plate_letter="ب", plate_middle="۳۴۵", plate_city="۶۷")
		self.assertEqual(car.plate, "12 ب 345 ایران 67")
		self.assertIn("۳۴۵", car.plate_html)
		self.assertTrue(car.name.startswith("CAR-"))
		with self.assertRaises(ValidationError):
			self.car(plate_left="1", plate_letter="ب", plate_middle="345", plate_city="67")

	def test_our_car(self):
		car = self.car(purchase_price=900000000, seller_id=self.owner.id, cost_ids=[
			(0, 0, {"service_id": self.env.ref("veron_dealership.service_10").id, "partner_id": self.garage.id, "amount": 20000000}),
			(0, 0, {"service_id": self.env.ref("veron_dealership.service_1").id, "amount": 1000000}),
		])
		self.assertEqual((car.repair_total, car.preparation_total, car.costs_total), (20000000, 1000000, 21000000))
		car.action_receive()
		self.assertEqual(car.entry_date, fields.Date.context_today(car))
		with self.assertRaises(UserError):
			car.action_ready()
		car.asking_price = 1000000000
		car.action_ready()
		with self.assertRaises(UserError):
			car.action_reserve()
		car.customer_id = self.customer
		car.action_reserve()
		car.sale_price = 980000000
		car.action_sell()
		self.assertEqual(car.state, "sold")
		self.assertEqual(car.profit, 980000000 - 900000000 - 21000000)
		car.action_create_sale_invoice()
		self.assertEqual((car.sale_invoice_id.state, car.sale_invoice_id.amount_untaxed), ("draft", 980000000))
		car.action_create_purchase_bill()
		self.assertEqual((car.purchase_bill_id.move_type, car.purchase_bill_id.partner_id), ("in_invoice", self.owner))
		car.action_create_cost_bills()
		self.assertEqual(car.cost_ids.bill_id.partner_id, self.garage)
		with self.assertRaises(UserError):
			car.action_create_cost_bills()
		car.action_exit()
		self.assertEqual(car.state, "exited")

	def test_consignment(self):
		car = self.car(ownership="customer", owner_id=self.owner.id, commission_rate=2, asking_price=500000000,
			customer_id=self.customer.id, cost_ids=[(0, 0, {"name": "کارواش", "amount": 1000000})])
		car.action_receive()
		car.action_ready()
		car.sale_price = 500000000
		car.action_sell()
		self.assertEqual(car.profit, 10000000 - 1000000)
		car.charge_costs_to_owner = True
		self.assertEqual(car.profit, 10000000)
		car.action_create_sale_invoice()
		self.assertEqual((car.sale_invoice_id.partner_id, car.sale_invoice_id.amount_untaxed), (self.owner, 10000000))

	def test_roles(self):
		seller = new_test_user(self.env, "seller", groups="base.group_user,veron_dealership.group_dealership_user")
		reception = new_test_user(self.env, "reception", groups="base.group_user,veron_dealership.group_dealership_reception")
		car = self.car(asking_price=500000000, minimum_price=480000000, customer_id=self.customer.id)
		car.action_receive()
		car.action_ready()
		as_reception = car.with_user(reception)
		as_reception.mileage = 21000
		with self.assertRaises(AccessError):
			as_reception.read(["purchase_price"])
		with self.assertRaises(AccessError):
			self.env["veron.instalment.sale"].with_user(reception).search([])
		as_seller = car.with_user(seller)
		as_seller.sale_price = 470000000
		with self.assertRaises(UserError):
			as_seller.action_sell()
		as_seller.sale_price = 485000000
		as_seller.action_sell()
		self.assertEqual(car.state, "sold")


@tagged("post_install", "-at_install")
class TestInstalmentAndInvestment(DealershipCase):
	def test_shamsi_months(self):
		# 4 Aban 1405 → 4 Azar, 4 Dey
		start = jalali.to_gregorian(1405, 8, 4)
		self.assertEqual(jalali.to_jalali(add_shamsi_months(start, 1)), (1405, 9, 4))
		self.assertEqual(jalali.to_jalali(add_shamsi_months(start, 5)), (1406, 1, 4))
		# 31 Shahrivar → 30 Mehr, the last day of a shorter month
		self.assertEqual(jalali.to_jalali(add_shamsi_months(jalali.to_gregorian(1405, 6, 31), 1)), (1405, 7, 30))

	def test_instalment_sale(self):
		car = self.car(asking_price=1000000000, customer_id=self.customer.id)
		car.action_receive()
		car.action_ready()
		sale = self.env["veron.instalment.sale"].create({
			"customer_id": self.customer.id, "vehicle_id": car.id, "sale_price": 1000000000, "down_payment": 400000000,
			"monthly_rate": 2, "months": 10, "date": jalali.to_gregorian(1405, 8, 4),
		})
		self.assertEqual((sale.financed, sale.total_interest, sale.total_payable, sale.instalment_amount),
			(600000000, 120000000, 720000000, 72000000))
		sale.action_confirm()
		self.assertEqual(car.state, "sold")
		self.assertEqual(car.sale_price, 1000000000)
		self.assertEqual(len(sale.line_ids), 10)
		self.assertEqual(sum(sale.line_ids.mapped("amount")), 720000000)
		self.assertEqual(jalali.to_jalali(sale.line_ids[0].due_date), (1405, 9, 4))
		self.assertEqual(jalali.to_jalali(sale.line_ids[-1].due_date), (1406, 6, 4))
		sale.action_create_invoice()
		self.assertEqual(sale.invoice_id.amount_untaxed, 1120000000)
		# The first instalment with a cheque, cashed; the others in cash
		bank = self.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1)
		cheque = self.env["veron.cheque"].create({"direction": "in", "partner_id": self.customer.id, "amount": 72000000,
			"serial": "1001", "due_date": sale.line_ids[0].due_date, "bank_journal_id": bank.id, "veron_instalment_id": sale.line_ids[0].id})
		self.assertFalse(sale.line_ids[0].paid)
		cheque.action_receive()
		cheque.action_deposit()
		cheque.action_cash()
		self.assertTrue(sale.line_ids[0].paid)
		self.assertEqual(sale.state, "active")
		sale.line_ids[1:].write({"paid_manually": True})
		self.assertEqual(sale.state, "settled")
		self.assertEqual(sale.outstanding, 0)

	def test_investment(self):
		contract = self.env["veron.investment.contract"].create({
			"investor_id": self.owner.id, "amount": 1000000000, "monthly_rate": 3, "months": 10, "payment_mode": "equal",
			"start_date": jalali.to_gregorian(1405, 8, 1),
		})
		self.assertEqual((contract.monthly_profit, contract.total_profit, contract.payment_amount), (30000000, 300000000, 130000000))
		self.assertEqual(jalali.to_jalali(contract.end_date), (1406, 6, 1))
		contract.action_confirm()
		self.assertEqual(contract.line_ids.mapped("amount"), [130000000] * 10)
		other = contract.copy({"payment_mode": "monthly"})
		other.action_confirm()
		self.assertEqual(other.line_ids.mapped("amount"), [30000000] * 9 + [1030000000])
		bank = self.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1)
		contract.received_journal_id = bank
		contract.action_receipt_entry()
		self.assertEqual((contract.receipt_move_id.state, contract.receipt_move_id.amount_total), ("draft", 1000000000))


@tagged("post_install", "-at_install")
class TestShowroomSite(HttpCase):
	def test_showroom(self):
		model = self.env.ref("veron_dealership.car_model_5")
		car = self.env["veron.vehicle"].create({"model_id": model.id, "year": "1402", "mileage": 35000, "asking_price": 750000000,
			"website_headline": "بدون رنگ، سند آزاد"})
		hidden = self.env["veron.vehicle"].create({"model_id": model.id, "year": "1399", "asking_price": 1})
		car.action_receive()
		car.action_ready()
		car.website_published = True
		page = self.url_open("/showroom").text
		self.assertIn("بدون رنگ، سند آزاد", page)
		self.assertNotIn(f"/showroom/{hidden.id}", page)
		self.assertEqual(self.url_open(f"/showroom/{hidden.id}").status_code, 404)
		page = self.url_open(f"/showroom/{car.id}").text
		token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
		response = self.url_open(f"/showroom/{car.id}/inquiry", data={"csrf_token": token, "name": "مشتری سایت", "phone": "09120000000",
			"message": "برای بازدید"})
		self.assertIn("سپاس", response.text.replace("ثبت شد", "سپاس"))
		lead = self.env["crm.lead"].search([("veron_vehicle_id", "=", car.id)])
		self.assertEqual((lead.contact_name, lead.phone), ("مشتری سایت", "09120000000"))
