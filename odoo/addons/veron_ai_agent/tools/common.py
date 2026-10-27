"""Helpers the tools share: filters a model gives as plain triples, turned into a domain only after each
field, operator and value is checked against what the agent may read"""

from datetime import date, timedelta

from odoo import fields
from odoo.fields import Domain

from ..services.registry import ToolDenied

OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "ilike", "not ilike", "in", "not in"}
FILTER_SCHEMA = {
	"type": "array", "maxItems": 10,
	"items": {"type": "array", "minItems": 3, "maxItems": 3,
		"items": {"type": ["string", "number", "boolean", "null", "array"], "maxItems": 50}},
}
PERIOD = {
	"days": {"type": "integer", "minimum": 1, "maximum": 400, "description": "The last N days, today included"},
	"date_from": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD"},
	"date_to": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD"},
}


def filters_domain(ctx, model_name, filters):
	readable = set(ctx.fields(model_name))
	model = ctx.env[model_name]
	domain = Domain.TRUE
	for field_name, operator, value in filters or []:
		if not isinstance(field_name, str) or field_name not in readable:
			raise ToolDenied(ctx.env._("The agent may not filter on %s.", field_name))
		if operator not in OPERATORS:
			raise ToolDenied(ctx.env._("The operator %s is not allowed.", operator))
		field = model._fields[field_name]
		if field.type in ("one2many", "many2many", "binary", "html", "json", "properties"):
			raise ToolDenied(ctx.env._("The agent may not filter on %s.", field_name))
		if isinstance(value, list) and operator not in ("in", "not in"):
			raise ToolDenied(ctx.env._("A list goes only with in or not in."))
		domain &= Domain(field_name, operator, value)
	return domain


def period(ctx, args, default_days=30):
	today = fields.Date.context_today(ctx.env.user)
	if args.get("date_from") or args.get("date_to"):
		try:
			start = date.fromisoformat(args["date_from"]) if args.get("date_from") else date(2000, 1, 1)
			end = date.fromisoformat(args["date_to"]) if args.get("date_to") else today
		except ValueError as error:
			raise ToolDenied(ctx.env._("Dates are written YYYY-MM-DD.")) from error
		return start, end
	end = today
	return end - timedelta(days=(args.get("days") or default_days) - 1), end


def plain(record, names):
	"""A record as JSON-like values: relations as their names, dates as text"""
	values = {"id": record.id, "name": record.display_name}
	for name in names:
		if name in ("id", "display_name"):
			continue
		field = record._fields[name]
		value = record[name]
		if field.type == "many2one":
			value = value.display_name if value else None
		elif field.type in ("one2many", "many2many"):
			value = value.mapped("display_name")[:20]
		elif field.type in ("date", "datetime"):
			value = str(value) if value else None
		elif field.type == "monetary" or field.type == "float":
			value = round(value or 0.0, 2)
		elif field.type in ("html",):
			value = (value or "")[:2000]
		elif value is False and field.type != "boolean":
			value = None
		values[name] = value
	return values


def scoped(ctx, model_name, extra=None):
	"""Records the agent may see of a model: its scope, the person's rights (the environment) and `extra`"""
	ctx.check_model(model_name)
	domain = ctx.domain(model_name)
	if extra is not None:
		domain &= Domain(extra)
	return ctx.env[model_name], domain


def money(env, amount):
	return round(amount or 0.0, 2)
