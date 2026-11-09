import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Rotation(models.Model):
	_name = "veron.planning.rotation"
	_description = "Rotating Shift Pattern"

	name = fields.Char(required=True, translate=True)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	tz = fields.Selection("_tz_list", "Time Zone", default="Asia/Tehran", required=True)
	day_ids = fields.One2many("veron.planning.rotation.day", "rotation_id", "Days of the Cycle", copy=True)
	member_ids = fields.One2many("veron.planning.rotation.member", "rotation_id", "People", copy=False)
	length = fields.Integer("Days in the Cycle", compute="_compute_length")

	@api.model
	def _tz_list(self):
		return [(tz, tz) for tz in pytz.common_timezones]

	@api.depends("day_ids")
	def _compute_length(self):
		for rotation in self:
			rotation.length = len(rotation.day_ids)

	def _day(self, member, date):
		"""The day of the cycle a person is on at a date"""
		days = self.day_ids.sorted(lambda d: (d.sequence, d.id))
		return days[((date - member.start_date).days + member.offset) % len(days)]

	def _shifts(self, date_from, date_to, members=None):
		"""The shifts of the pattern's people in a period, as the planning's values, in UTC"""
		self.ensure_one()
		if not self.day_ids:
			raise ValidationError(_("The pattern %s has no days.", self.name))
		zone = pytz.timezone(self.tz)
		values = []
		for member in members or self.member_ids:
			date = max(date_from, member.start_date)
			last = min(date_to, member.end_date or date_to)
			while date <= last:
				day = self._day(member, date)
				if not day.rest:
					hours, minutes = divmod(round(day.start_hour * 60), 60)
					start = zone.localize(datetime.datetime.combine(date, datetime.time(hours % 24, minutes)))
					start = start.astimezone(pytz.utc).replace(tzinfo=None)
					values.append({"employee_id": member.employee_id.id, "role_id": day.role_id.id,
						"start_datetime": start, "end_datetime": start + datetime.timedelta(hours=day.hours),
						"company_id": self.company_id.id, "note": f"{self.name}: {day.name}"})
				date += datetime.timedelta(days=1)
		return values


class RotationDay(models.Model):
	_name = "veron.planning.rotation.day"
	_description = "Day of a Rotating Shift Pattern"
	_order = "sequence, id"

	rotation_id = fields.Many2one("veron.planning.rotation", required=True, ondelete="cascade")
	sequence = fields.Integer(default=10)
	name = fields.Char("Shift", required=True, translate=True)
	rest = fields.Boolean()
	role_id = fields.Many2one("veron.planning.role")
	start_hour = fields.Float("Starts At", default=7.0)
	hours = fields.Float(default=8.0)

	@api.constrains("rest", "start_hour", "hours")
	def _check_hours(self):
		for day in self.filtered(lambda d: not d.rest):
			if not 0 <= day.start_hour < 24 or not 0 < day.hours <= 24:
				raise ValidationError(_("A shift starts in the day and lasts up to 24 hours (%s).", day.name))


class RotationMember(models.Model):
	_name = "veron.planning.rotation.member"
	_description = "Person on a Rotating Shift Pattern"

	rotation_id = fields.Many2one("veron.planning.rotation", required=True, ondelete="cascade")
	employee_id = fields.Many2one("hr.employee", required=True)
	start_date = fields.Date("From", required=True, default=fields.Date.context_today)
	end_date = fields.Date("Until")
	offset = fields.Integer("Starts on Day", default=0,
		help="The day of the cycle the person is on at the start, counted from 0: people starting on other days "
			"make the groups that follow each other")
