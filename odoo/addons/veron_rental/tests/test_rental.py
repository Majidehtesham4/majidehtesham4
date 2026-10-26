from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRental(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.car = cls.env["product.product"].create({
			"name": "پژو ۲۰۷ اجاره‌ای", "type": "service", "rent_ok": True, "rental_units": 2,
			"rental_price_day": 30000000, "rental_late_fee_day": 45000000, "taxes_id": [(6, 0, [])]})
		cls.customer = cls.env["res.partner"].create({"name": "مشتری اجاره"})
		cls.start = datetime(2026, 11, 1, 9, 0)

	def order(self, quantity=1, days=3, start=None):
		start = start or self.start
		return self.env["veron.rental.order"].create({
			"partner_id": self.customer.id, "start_date": start, "end_date": start + timedelta(days=days),
			"line_ids": [(0, 0, {"product_id": self.car.id, "quantity": quantity})]})

	def test_price_and_double_booking(self):
		first = self.order(quantity=2)
		self.assertEqual(first.days, 3)
		self.assertEqual(first.amount_total, 2 * 3 * 30000000)
		first.action_reserve()
		with self.assertRaises(UserError):
			self.order(start=self.start + timedelta(days=1)).action_reserve()  # both units rented
		later = self.order(start=self.start + timedelta(days=3))
		later.action_reserve()  # free again once the first is back
		self.assertEqual(later.state, "reserved")

	def test_late_return_and_invoice(self):
		order = self.order(days=2)
		order.action_reserve()
		order.action_pickup()
		with patch("odoo.fields.Datetime.now", return_value=self.start + timedelta(days=3, hours=5)):
			order.action_return()
		self.assertEqual(order.late_days, 2)  # 1 day 5 hours late: 2 days
		self.assertEqual(order.amount_late, 2 * 45000000)
		order.action_invoice()
		self.assertEqual(order.state, "invoiced")
		self.assertEqual(order.invoice_id.amount_untaxed, 2 * 30000000 + 2 * 45000000)
		self.assertEqual(order.invoice_id.state, "draft")

	def test_cannot_cancel_once_out(self):
		order = self.order()
		order.action_reserve()
		order.action_pickup()
		with self.assertRaises(UserError):
			order.action_cancel()
