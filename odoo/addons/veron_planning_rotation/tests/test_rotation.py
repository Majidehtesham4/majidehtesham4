import datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRotation(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.a = cls.env["hr.employee"].create({"name": "گروه الف"})
		cls.b = cls.env["hr.employee"].create({"name": "گروه ب"})
		cls.rotation = cls.env["veron.planning.rotation"].create({"name": "سه نوبت", "day_ids": [
			(0, 0, {"sequence": 1, "name": "صبح", "start_hour": 7, "hours": 8}),
			(0, 0, {"sequence": 2, "name": "عصر", "start_hour": 15, "hours": 8}),
			(0, 0, {"sequence": 3, "name": "شب", "start_hour": 23, "hours": 8}),
			(0, 0, {"sequence": 4, "name": "استراحت", "rest": True}),
		], "member_ids": [
			(0, 0, {"employee_id": cls.a.id, "start_date": "2026-10-01"}),
			(0, 0, {"employee_id": cls.b.id, "start_date": "2026-10-01", "offset": 2}),
		]})

	def generate(self, start, end):
		wizard = self.env["veron.planning.rotation.generate"].create({"rotation_ids": [(6, 0, self.rotation.ids)],
			"date_from": start, "date_to": end})
		wizard.action_generate()
		return wizard

	def test_the_cycle(self):
		self.generate("2026-10-01", "2026-10-08")
		shifts = self.env["veron.planning.shift"].search([("employee_id", "=", self.a.id)], order="start_datetime")
		self.assertEqual(len(shifts), 6, "8 days, two rests")
		self.assertEqual(shifts[0].start_datetime, datetime.datetime(2026, 10, 1, 3, 30), "07:00 in Tehran")
		self.assertEqual(shifts[2].end_datetime, datetime.datetime(2026, 10, 4, 3, 30), "the night ends the next day")
		self.assertEqual(set(shifts.mapped("state")), {"draft"})
		first_b = self.env["veron.planning.shift"].search([("employee_id", "=", self.b.id)], order="start_datetime", limit=1)
		self.assertIn("شب", first_b.note, "the other group starts on the third day")

	def test_never_over_a_shift(self):
		self.generate("2026-10-01", "2026-10-04")
		wizard = self.generate("2026-10-01", "2026-10-08")
		self.assertEqual(self.env["veron.planning.shift"].search_count([("employee_id", "=", self.a.id)]), 6)
		self.assertIn("6", wizard.result)

	def test_limits(self):
		with self.assertRaises(UserError):
			self.generate("2026-10-01", "2027-03-01")
		with self.assertRaises(ValidationError):
			self.rotation.day_ids[0].hours = 30
