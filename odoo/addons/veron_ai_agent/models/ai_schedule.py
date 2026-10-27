from datetime import datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.veron_core.models import jalali

from .ai_agent import WEEKDAYS


class AiSchedule(models.Model):
	"""When an agent runs by itself. The time is in the agent's time zone; a monthly schedule counts Shamsi
	or Gregorian months. A run that comes outside the agent's working hours waits for them, or is skipped."""

	_name = "veron.ai.schedule"
	_description = "Agent Schedule"
	_order = "next_run, id"

	name = fields.Char(required=True, default=lambda self: _("Schedule"))
	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade", index=True)
	active = fields.Boolean(default=True)
	interval = fields.Selection([("daily", "Every Day"), ("weekly", "Every Week"), ("monthly", "Every Month"),
		("custom", "Every...")], required=True, default="daily")
	every = fields.Integer(default=1)
	unit = fields.Selection([("hours", "Hours"), ("days", "Days"), ("weeks", "Weeks"), ("months", "Months")],
		default="days")
	hour = fields.Float("At", default=8.0)
	weekday = fields.Selection(WEEKDAYS, default="5")
	month_day = fields.Integer("Day of the Month", default=1, help="1 to 31; -1 for the last day of the month")
	calendar = fields.Selection([("shamsi", "Shamsi"), ("gregorian", "Gregorian")], default="shamsi")
	input_text = fields.Text("Request", help="What the agent is asked each time, e.g. the report of yesterday")
	outside_hours = fields.Selection([("wait", "Wait for the Working Hours"), ("skip", "Skip"), ("run", "Run Anyway")],
		"Outside Working Hours", default="wait", required=True)
	next_run = fields.Datetime(readonly=True, index=True)
	last_run = fields.Datetime(readonly=True)
	last_run_id = fields.Many2one("veron.ai.run", "Last Run Record", readonly=True)

	@api.constrains("every", "hour", "month_day")
	def _check(self):
		for schedule in self:
			if schedule.every < 1:
				raise ValidationError(_("A schedule repeats at least every 1."))
			if not 0 <= schedule.hour < 24:
				raise ValidationError(_("The hour is between 0 and 24."))
			if schedule.month_day == 0 or not -1 <= schedule.month_day <= 31:
				raise ValidationError(_("The day of the month is 1 to 31, or -1 for the last day."))

	@api.model_create_multi
	def create(self, vals_list):
		schedules = super().create(vals_list)
		for schedule in schedules:
			schedule.next_run = schedule._next(fields.Datetime.now())
		return schedules

	def write(self, vals):
		res = super().write(vals)
		if {"interval", "every", "unit", "hour", "weekday", "month_day", "calendar", "active"} & set(vals):
			for schedule in self:
				schedule.next_run = schedule._next(fields.Datetime.now())
		return res

	def _next(self, after):
		"""The first run time after `after` (UTC, naive), as UTC naive"""
		self.ensure_one()
		tz = pytz.timezone(self.agent_id.tz or "Asia/Tehran")
		local = pytz.utc.localize(after).astimezone(tz).replace(tzinfo=None)
		hours, minutes = int(self.hour), int(round((self.hour % 1) * 60))
		if self.interval == "custom":
			step = {"hours": relativedelta(hours=self.every), "days": relativedelta(days=self.every),
				"weeks": relativedelta(weeks=self.every), "months": relativedelta(months=self.every)}[self.unit or "days"]
			base = self.last_run and pytz.utc.localize(self.last_run).astimezone(tz).replace(tzinfo=None)
			candidate = (base + step) if base else local.replace(minute=minutes, second=0, microsecond=0)
			while candidate <= local:
				candidate += step
		elif self.interval == "daily":
			candidate = local.replace(hour=hours, minute=minutes, second=0, microsecond=0)
			while candidate <= local:
				candidate += timedelta(days=self.every if self.last_run else 1)
		elif self.interval == "weekly":
			candidate = local.replace(hour=hours, minute=minutes, second=0, microsecond=0)
			candidate += timedelta(days=(int(self.weekday) - candidate.weekday()) % 7)
			while candidate <= local:
				candidate += timedelta(weeks=1)
		else:
			candidate = self._monthly(local, hours, minutes)
		return tz.localize(candidate).astimezone(pytz.utc).replace(tzinfo=None)

	def _monthly(self, local, hours, minutes):
		def day_of(year, month):
			if self.calendar == "shamsi":
				length = jalali.month_length(year, month)
				day = length if self.month_day == -1 else min(self.month_day, length)
				date = jalali.to_gregorian(year, month, day)
			else:
				first = datetime(year, month, 1)
				length = ((first + relativedelta(months=1)) - first).days
				day = length if self.month_day == -1 else min(self.month_day, length)
				date = first.replace(day=day).date()
			return datetime(date.year, date.month, date.day, hours, minutes)

		if self.calendar == "shamsi":
			year, month, _day = jalali.to_jalali(local.date())
		else:
			year, month = local.year, local.month
		for _i in range(14):
			candidate = day_of(year, month)
			if candidate > local:
				return candidate
			month += 1
			if month > 12:
				year, month = year + 1, 1
		return local + timedelta(days=30)

	@api.model
	def _cron_due(self):
		"""Queues the runs of the schedules whose time has come"""
		now = fields.Datetime.now()
		schedules = self.sudo().search([("active", "=", True), ("next_run", "<=", now), ("agent_id.enabled", "=", True),
			("agent_id.trigger_schedule", "=", True)])
		for schedule in schedules:
			agent = schedule.agent_id
			if not agent._in_working_hours(now) and schedule.outside_hours != "run":
				if schedule.outside_hours == "skip":
					schedule.write({"next_run": schedule._next(now)})
				else:
					schedule.next_run = now + timedelta(minutes=30)
				continue
			user = agent.run_as_user_id or agent.responsible_user_id
			run = self.env["veron.ai.run"]._enqueue(agent, user, "schedule", text=schedule.input_text)
			schedule.write({"last_run": now, "last_run_id": run.id})
			schedule.next_run = schedule._next(now)
		self.env["veron.ai.run"]._cron_process()
		return True

	def action_run_now(self):
		self.ensure_one()
		agent = self.agent_id
		run = self.env["veron.ai.run"]._start(agent, agent.run_as_user_id or self.env.user, "user", text=self.input_text)
		return run._open()
