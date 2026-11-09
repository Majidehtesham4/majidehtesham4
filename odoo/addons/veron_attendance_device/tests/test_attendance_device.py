import base64
import datetime
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..wizard.punch_import import moment


@tagged("post_install", "-at_install")
class TestAttendanceDevice(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.device = cls.env["veron.attendance.device"].create({"name": "ورودی کارخانه", "address": "192.168.1.20"})
		cls.ali = cls.env["hr.employee"].create({"name": "علی نمونه", "veron_device_code": "101"})
		cls.sara = cls.env["hr.employee"].create({"name": "سارا نمونه", "veron_device_code": "102"})
		cls.Attendance = cls.env["hr.attendance"]

	def at(self, day, hour, minute=0):
		return datetime.datetime(2026, 10, day, hour, minute)

	def test_punches_made_into_attendances(self):
		made = self.device._record([("101", self.at(5, 7, 55)), ("101", self.at(5, 12, 0)), ("101", self.at(5, 13, 0)),
			("101", self.at(5, 16, 30)), ("102", self.at(5, 8, 10)), ("999", self.at(5, 8, 0))])
		self.assertEqual(len(made), 6)
		attendances = self.Attendance.search([("employee_id", "=", self.ali.id)], order="check_in")
		self.assertEqual(len(attendances), 2, "in, out, in, out: two attendances")
		self.assertEqual(attendances[0].check_in, datetime.datetime(2026, 10, 5, 4, 25), "Tehran's time in UTC")
		self.assertEqual(attendances[1].check_out, datetime.datetime(2026, 10, 5, 13, 0))
		lone = made.filtered(lambda p: p.code == "102")
		self.assertFalse(lone.attendance_id, "a day gone by: an open check-in would stop the days after it")
		self.assertTrue(lone.problem)
		self.assertEqual(self.device.unknown_count, 1)
		self.assertFalse(self.device._record([("101", self.at(5, 7, 55))]), "a punch is kept once")

	def test_later_punches_of_the_day(self):
		self.device._record([("101", self.at(6, 8, 0)), ("101", self.at(6, 12, 0))])
		# The file of the day read again later, with the afternoon too
		self.device._record([("101", self.at(6, 8, 0)), ("101", self.at(6, 12, 0)), ("101", self.at(6, 13, 0)),
			("101", self.at(6, 17, 0))])
		self.assertEqual(self.Attendance.search_count([("employee_id", "=", self.ali.id)]), 2)

	def test_today_left_open(self):
		now = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(minutes=5)
		import pytz

		local = pytz.utc.localize(now).astimezone(pytz.timezone(self.device.tz)).replace(tzinfo=None)
		self.device._record([("101", local)])
		attendance = self.Attendance.search([("employee_id", "=", self.ali.id)])
		self.assertEqual((attendance.check_in, attendance.check_out), (now, False), "today: checked in")

	def test_unknown_code_matched_later(self):
		punches = self.device._record([("103", self.at(7, 8, 0)), ("103", self.at(7, 16, 0))])
		self.assertFalse(punches.employee_id)
		reza = self.env["hr.employee"].create({"name": "رضا نمونه", "veron_device_code": "103"})
		punches.action_match()
		self.assertEqual(punches.employee_id, reza)
		self.assertEqual(self.Attendance.search_count([("employee_id", "=", reza.id)]), 1)

	def test_a_manual_attendance_in_the_way(self):
		self.Attendance.create({"employee_id": self.sara.id, "check_in": datetime.datetime(2026, 10, 8, 5, 0),
			"check_out": datetime.datetime(2026, 10, 8, 10, 0)})
		punches = self.device._record([("102", self.at(8, 9, 0)), ("102", self.at(8, 15, 0))])
		self.assertFalse(punches.attendance_id)
		self.assertTrue(all(punches.mapped("problem")), "listed, not forced over what a person entered")

	def test_times_of_the_files(self):
		self.assertEqual(moment("1405/07/13 07:58"), datetime.datetime(2026, 10, 5, 7, 58))
		self.assertEqual(moment("۱۴۰۵/۰۷/۱۳ ۰۷:۵۸:۱۲"), datetime.datetime(2026, 10, 5, 7, 58, 12))
		self.assertEqual(moment("2026-10-05 07:58:12"), datetime.datetime(2026, 10, 5, 7, 58, 12))
		self.assertEqual(moment("05/10/2026 7:58"), datetime.datetime(2026, 10, 5, 7, 58))
		self.assertIsNone(moment("ورود"))

	def test_import_the_file(self):
		text = "کد پرسنلی,نام,تاریخ,ساعت\n101,علی,1405/07/14,08:00\n101,علی,1405/07/14,16:00\n,,,\nبد,,,\n"
		wizard = self.env["veron.attendance.punch.import"].create({"device_id": self.device.id, "filename": "log.csv",
			"file": base64.b64encode(text.encode())})
		wizard.action_import()
		self.assertIn("2", wizard.result)
		attendance = self.Attendance.search([("employee_id", "=", self.ali.id)])
		self.assertEqual(attendance.check_in, datetime.datetime(2026, 10, 6, 4, 30))
		plain = "\t".join(["102", "2026-10-07 08:00:00"]) + "\n" + "\t".join(["102", "2026-10-07 17:00:00"])
		self.env["veron.attendance.punch.import"].create({"device_id": self.device.id, "filename": "x.txt",
			"file": base64.b64encode(plain.encode())}).action_import()
		self.assertEqual(self.Attendance.search_count([("employee_id", "=", self.sara.id)]), 1, "no titles: code, then time")

	def test_pull_without_the_library(self):
		with patch.dict("sys.modules", {"zk": None}):
			with self.assertRaises(UserError):
				self.device._read_device()
			self.device.action_pull()
		self.assertIn("pyzk", self.device.last_error, "the error kept on the device, the next one pulled")

	def test_pull_with_the_library(self):
		class Item:
			def __init__(self, user_id, timestamp):
				self.user_id, self.timestamp = user_id, timestamp

		class Connection:
			def disable_device(self): pass
			def enable_device(self): pass
			def disconnect(self): pass
			def get_attendance(self):
				return [Item(101, datetime.datetime(2026, 10, 9, 8, 0)), Item(101, datetime.datetime(2026, 10, 9, 17, 0))]

		class ZK:
			def __init__(self, *args, **kwargs): pass
			def connect(self):
				return Connection()

		module = type("zk", (), {"ZK": ZK})
		with patch.dict("sys.modules", {"zk": module}):
			self.device.action_pull()
		self.assertTrue(self.device.last_pull)
		self.assertFalse(self.device.last_error)
		self.assertEqual(self.Attendance.search_count([("employee_id", "=", self.ali.id)]), 1)
