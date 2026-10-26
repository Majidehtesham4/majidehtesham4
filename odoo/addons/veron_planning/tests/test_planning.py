from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlanning(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = cls.env["res.users"].create({"name": "رضا", "login": "reza_planning", "email": "reza@example.com"})
		cls.employee = cls.env["hr.employee"].create({"name": "رضا", "user_id": cls.user.id})
		cls.role = cls.env.ref("veron_planning.role_cashier")
		cls.Shift = cls.env["veron.planning.shift"]
		cls.day = datetime(2026, 11, 2)

	def shift(self, start_hour, end_hour, day=None):
		day = day or self.day
		return self.Shift.create({
			"employee_id": self.employee.id, "role_id": self.role.id,
			"start_datetime": day + timedelta(hours=start_hour), "end_datetime": day + timedelta(hours=end_hour),
		})

	def test_hours_and_dates(self):
		self.assertEqual(self.shift(5, 13).allocated_hours, 8)
		with self.assertRaises(ValidationError):
			self.shift(13, 5)

	def test_overlap_is_a_conflict(self):
		first = self.shift(5, 13)
		self.assertFalse(first.conflict)
		second = self.shift(12, 16)
		self.assertTrue(second.conflict)
		first.invalidate_recordset(["conflict"])  # computed, not stored: as when the plan is loaded again
		self.assertTrue(first.conflict)
		self.assertFalse(self.shift(16, 18).conflict)
		self.assertEqual(set(self.Shift.search([("conflict", "=", True)]).ids), {first.id, second.id})

	def test_time_off_is_a_conflict(self):
		leave_type = self.env["hr.leave.type"].create({"name": "مرخصی بدون حقوق", "requires_allocation": False, "leave_validation_type": "no_validation"})
		leave = self.env["hr.leave"].create({
			"employee_id": self.employee.id, "holiday_status_id": leave_type.id,
			"request_date_from": self.day.date(), "request_date_to": self.day.date(),
		})
		if leave.state != "validate":
			leave.sudo().action_approve()
		shift = self.shift(5, 13)
		self.assertTrue(shift.conflict)
		self.assertIn("مرخصی بدون حقوق", shift.conflict_reason)

	def test_publish_and_employee_sees_it(self):
		shift = self.shift(5, 13)
		as_employee = self.Shift.with_user(self.user)
		other = self.env["hr.employee"].create({"name": "مریم"})
		hidden = self.Shift.create({"employee_id": other.id, "start_datetime": self.day, "end_datetime": self.day + timedelta(hours=4)})
		self.assertNotIn(hidden, as_employee.search([]))
		shift.action_publish()
		self.assertEqual(shift.state, "published")
		self.assertIn(self.user.partner_id, shift.message_ids[0].partner_ids)
		hidden.action_publish()
		self.assertIn(hidden, as_employee.search([]))

	def test_copy_previous_week(self):
		now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
		self.Shift.create({"employee_id": self.employee.id, "start_datetime": now - timedelta(days=2), "end_datetime": now - timedelta(days=2, hours=-4)})
		self.Shift.action_copy_previous_week()
		copies = self.Shift.search([("employee_id", "=", self.employee.id), ("start_datetime", "=", now + timedelta(days=5))])
		self.assertEqual(len(copies), 1)
		self.assertEqual(copies.state, "draft")
		self.Shift.action_copy_previous_week()
		self.assertEqual(self.Shift.search_count([("employee_id", "=", self.employee.id), ("start_datetime", "=", now + timedelta(days=5))]), 1)
