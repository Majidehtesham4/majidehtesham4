"""Grouping by month, season or year follows the Shamsi calendar in Persian: «آبان 1405» holds the
records from 1 to 30 Aban, not those of October. A database function puts a date in its period."""

import datetime

import pytz

from odoo import models
from odoo.tools import SQL
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, get_lang

from . import jalali

SHAMSI = ("month", "quarter", "year")


class Base(models.AbstractModel):
	_inherit = "base"

	def _veron_shamsi_group(self, groupby_spec):
		"""(field, granularity) when this grouping is by a Shamsi period, else None"""
		if ":" not in groupby_spec or not get_lang(self.env).code.startswith("fa"):
			return None
		fname, granularity = groupby_spec.split(":", 1)
		field = self._fields.get(fname)
		if granularity in SHAMSI and field and field.type in ("date", "datetime"):
			return field, granularity
		return None

	def _read_group_groupby(self, alias, groupby_spec, query):
		shamsi = self._veron_shamsi_group(groupby_spec)
		if not shamsi:
			return super()._read_group_groupby(alias, groupby_spec, query)
		field, granularity = shamsi
		# The day, in the user's time zone for a datetime, then the start of its Shamsi period
		day = super()._read_group_groupby(alias, f"{field.name}:day", query)
		start = SQL("veron_shamsi_start(%s, %s::date)", granularity, day)
		return SQL("%s::timestamp", start) if field.type == "datetime" else start

	def _web_read_group_groupby_formatter(self, groupby_spec, values):
		shamsi = self._veron_shamsi_group(groupby_spec)
		if not shamsi:
			return super()._web_read_group_groupby_formatter(groupby_spec, values)
		field, granularity = shamsi
		fmt = DEFAULT_SERVER_DATETIME_FORMAT if field.type == "datetime" else DEFAULT_SERVER_DATE_FORMAT
		tz = None
		if field.type == "datetime" and self.env.context.get("tz") in pytz.all_timezones_set:
			tz = pytz.timezone(self.env.context["tz"])

		def formatter(value):
			if not value:
				return value, [(field.name, "=", value)]
			start = value
			end = jalali.period_next(value, granularity)
			if field.type == "datetime":
				end = datetime.datetime.combine(end, datetime.time())
				if tz:
					start = tz.localize(start).astimezone(pytz.utc)
					end = tz.localize(end).astimezone(pytz.utc)
			label = jalali.period_label(value, granularity)
			domain = ["&", (field.name, ">=", start.strftime(fmt)), (field.name, "<", end.strftime(fmt))]
			return (start.strftime(fmt), label), domain

		return formatter

	def _web_read_group_fill_temporal(self, groups, groupby, aggregates, fill_from=False, fill_to=False, min_groups=False):
		shamsi = groupby and self._veron_shamsi_group(groupby[0])
		if not shamsi:
			return super()._web_read_group_fill_temporal(groups, groupby, aggregates, fill_from, fill_to, min_groups)
		field, granularity = shamsi
		existing = sorted(group[0] for group in groups if group[0])
		if not existing:
			return groups
		# The empty periods between the first and the last one shown
		as_date = lambda v: v.date() if isinstance(v, datetime.datetime) else v  # noqa: E731
		start, last = as_date(existing[0]), as_date(existing[-1])
		if fill_from:
			start = min(start, jalali.period_start(datetime.date.fromisoformat(str(fill_from)[:10]), granularity))
		if fill_to:
			last = max(last, jalali.period_start(datetime.date.fromisoformat(str(fill_to)[:10]), granularity))
		periods = []
		while start <= last or len(periods) < (min_groups or 0):
			periods.append(datetime.datetime.combine(start, datetime.time()) if field.type == "datetime" else start)
			start = jalali.period_next(start, granularity)
		empty = tuple(self._read_group_empty_value(spec) for spec in groupby[1:] + aggregates)
		by_value = {}
		for group in groups:
			by_value.setdefault(group[0], []).append(group)
		result = []
		for period in periods:
			result.extend(by_value.pop(period, None) or [(period, *empty)])
		for rest in by_value.values():
			result.extend(rest)
		return result
