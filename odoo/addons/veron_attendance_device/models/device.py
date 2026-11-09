import datetime
import logging

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
	_inherit = "hr.employee"

	veron_device_code = fields.Char("Attendance Device Code", groups="hr.group_hr_user", index=True,
		help="The number of the person on the attendance devices")


class AttendanceDevice(models.Model):
	_name = "veron.attendance.device"
	_description = "Attendance Device"

	name = fields.Char(required=True)
	active = fields.Boolean(default=True)
	kind = fields.Selection([("zkteco", "ZKTeco (over the network)"), ("file", "Its Software's File Only")],
		required=True, default="zkteco")
	address = fields.Char(help="The device's IP address on the network of the company")
	port = fields.Integer(default=4370)
	password = fields.Integer("Device Password", default=0, groups="hr_attendance.group_hr_attendance_officer")
	tz = fields.Selection("_tz_list", "Time Zone of the Device", default="Asia/Tehran", required=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	last_pull = fields.Datetime(readonly=True)
	last_error = fields.Text(readonly=True)
	punch_ids = fields.One2many("veron.attendance.punch", "device_id")
	unknown_count = fields.Integer("Punches of Unknown Codes", compute="_compute_unknown")

	@api.model
	def _tz_list(self):
		return [(tz, tz) for tz in pytz.common_timezones]

	def _compute_unknown(self):
		for device in self:
			device.unknown_count = self.env["veron.attendance.punch"].search_count([("device_id", "=", device.id),
				("employee_id", "=", False)])

	def _read_device(self):
		"""The punches of the device as (code, local time) pairs, with the pyzk library"""
		self.ensure_one()
		try:
			from zk import ZK
		except ImportError as error:
			raise UserError(_("Pulling over the network needs the «pyzk» library on the server (pip install pyzk); "
				"import the file of the device's software instead.")) from error
		connection = ZK(self.address, port=self.port or 4370, timeout=15, password=self.sudo().password or 0,
			force_udp=False, ommit_ping=True).connect()
		try:
			connection.disable_device()
			return [(str(item.user_id), item.timestamp) for item in connection.get_attendance()]
		finally:
			connection.enable_device()
			connection.disconnect()

	def action_pull(self):
		for device in self.filtered(lambda d: d.kind == "zkteco"):
			try:
				punches = device._read_device()
			except Exception as error:  # noqa: BLE001 - the device's error is shown, the next device is pulled
				device.last_error = str(error)
				_logger.warning("Attendance device %s not read: %s", device.name, error)
				continue
			device._record(punches)
			device.write({"last_pull": fields.Datetime.now(), "last_error": False})

	@api.model
	def _cron_pull(self):
		self.search([("kind", "=", "zkteco")]).action_pull()

	def _record(self, punches):
		"""Punches (code, local time) kept once each, their employee found, and made into attendances"""
		self.ensure_one()
		zone = pytz.timezone(self.tz or "Asia/Tehran")
		Punch = self.env["veron.attendance.punch"]
		employees = {e.veron_device_code: e for e in self.env["hr.employee"].sudo().search([
			("veron_device_code", "!=", False), ("company_id", "=", self.company_id.id)])}
		known = set(Punch.search([("device_id", "=", self.id)]).mapped(lambda p: (p.code, p.time)))
		values = []
		for code, local in punches:
			local = local.replace(tzinfo=None, microsecond=0)
			moment = zone.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
			if (code, moment) in known:
				continue
			known.add((code, moment))
			employee = employees.get(code)
			values.append({"device_id": self.id, "code": code, "time": moment, "day": local.date(), "employee_id": employee.id if employee else False})
		made = Punch.create(values)
		made.filtered("employee_id")._to_attendances()
		return made


class AttendancePunch(models.Model):
	"""A punch as the device gave it; never changed by hand"""

	_name = "veron.attendance.punch"
	_description = "Attendance Punch"
	_order = "time desc"

	device_id = fields.Many2one("veron.attendance.device", required=True, ondelete="cascade", index=True)
	code = fields.Char(required=True, index=True)
	time = fields.Datetime(required=True)
	day = fields.Date("Day", required=True, index=True, help="The day of the punch in the device's time zone")
	employee_id = fields.Many2one("hr.employee", index=True)
	attendance_id = fields.Many2one("hr.attendance", readonly=True, index="btree_not_null")
	problem = fields.Char(readonly=True, help="Why the punch is not in an attendance")

	_unique = models.Constraint("unique(device_id, code, time)", "A punch of the device is kept once.")

	def _to_attendances(self):
		"""The punches of each employee and day, with those of the day already there, as check-ins and check-outs
		in order: the first opens, the next closes, and so on. A last one alone is left open only today; on a day
		gone by it is listed, to be asked as a correction, since an open check-in would stop the days after it"""
		Attendance = self.env["hr.attendance"].sudo()
		for employee, day in sorted({(p.employee_id, p.day) for p in self if p.employee_id}, key=lambda k: (k[0].id, k[1])):
			punches = self.search([("employee_id", "=", employee.id), ("day", "=", day)], order="time")
			zone = pytz.timezone(punches[:1].device_id.tz or "Asia/Tehran")
			today = datetime.datetime.now(zone).date()
			old = punches.attendance_id
			punches.write({"attendance_id": False, "problem": False})
			old.unlink()
			times = list(punches)
			for index in range(0, len(times), 2):
				first = times[index]
				second = times[index + 1] if index + 1 < len(times) else None
				if not second and day < today:
					first.problem = _("No check-out after it")
					continue
				try:
					with self.env.cr.savepoint():
						attendance = Attendance.create({"employee_id": employee.id, "check_in": first.time,
							"check_out": second.time if second else False})
				except (UserError, ValidationError) as error:
					(first | (second or first)).write({"problem": str(error)[:250]})
					continue
				(first | (second or first)).write({"attendance_id": attendance.id})

	def action_match(self):
		"""The punches of codes now given to employees, matched and made into attendances"""
		codes = {e.veron_device_code: e for e in self.env["hr.employee"].sudo().search([("veron_device_code", "in",
			self.mapped("code"))])}
		for punch in self.filtered(lambda p: not p.employee_id and p.code in codes):
			punch.employee_id = codes[punch.code]
		self.filtered("employee_id")._to_attendances()
