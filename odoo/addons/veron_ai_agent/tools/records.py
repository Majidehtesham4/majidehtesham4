"""Reading Odoo data: only models in the agent's data scope, only fields it may read, with the person's
own access rights and companies. No free query, no dotted path through relations, no write."""


from odoo.tools.translate import LazyTranslate

from ..services.registry import Plan, Tool, ToolDenied, tool
from ..services.schema import strict_object
from .common import FILTER_SCHEMA, filters_domain, plain, scoped

_lt = LazyTranslate(__name__)

MODEL = {"type": "string", "maxLength": 64, "description": "Technical name of a model in the agent's data, e.g. sale.order"}


@tool
class RecordsSearch(Tool):
	code = "records_search"
	name = _lt("Search Records")
	description = _lt("Finds records of a model in the agent's data. Filters are [field, operator, value] triples; operators: "
		"= != > < >= <= ilike 'not ilike' in 'not in'. Returns at most `limit` records with the fields asked.")
	category = "read"
	schema = strict_object({
		"model": MODEL,
		"filters": FILTER_SCHEMA,
		"fields": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 64}},
		"limit": {"type": "integer", "minimum": 1, "maximum": 80},
		"order": {"type": "string", "maxLength": 80, "description": "A field, optionally followed by desc"},
	}, ["model"])

	def plan(self, ctx, args):
		return Plan(summary=ctx.env._("Read %s", args["model"]), model=args["model"])

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, args["model"])
		domain &= filters_domain(ctx, args["model"], args.get("filters"))
		names = ctx.fields(args["model"], args.get("fields") or None)
		if not args.get("fields"):
			names = [n for n in names if model._fields[n].type not in ("one2many", "many2many", "html", "text", "json",
				"properties")][:15]
		order = args.get("order") or None
		if order:
			field_name, _sep, direction = order.partition(" ")
			if field_name not in names or direction.strip().lower() not in ("", "asc", "desc"):
				raise ToolDenied(ctx.env._("The agent may not sort by %s.", order))
			if not model._fields[field_name].store:
				order = None
		records = model.search(domain, limit=args.get("limit") or 20, order=order)
		ctx.link(records[:20])
		return {"model": args["model"], "count": model.search_count(domain), "records": [plain(r, names) for r in records]}


@tool
class RecordRead(Tool):
	code = "record_read"
	name = _lt("Read a Record")
	description = _lt("Reads one record of a model in the agent's data, with the fields asked or all it may read.")
	category = "read"
	schema = strict_object({
		"model": MODEL,
		"id": {"type": "integer", "minimum": 1},
		"fields": {"type": "array", "maxItems": 40, "items": {"type": "string", "maxLength": 64}},
	}, ["model", "id"])

	def plan(self, ctx, args):
		return Plan(summary=ctx.env._("Read %(model)s %(id)s", model=args["model"], id=args["id"]), model=args["model"],
			res_ids=[args["id"]])

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, args["model"], [("id", "=", args["id"])])
		record = model.search(domain, limit=1)
		if not record:
			raise ToolDenied(ctx.env._("No such record in the agent's data."))
		names = ctx.fields(args["model"], args.get("fields") or None)
		names = [n for n in names if model._fields[n].type not in ("one2many",)][:60]
		ctx.link(record)
		return plain(record, names)


@tool
class RecordsAggregate(Tool):
	code = "records_aggregate"
	name = _lt("Totals and Counts")
	description = _lt("Counts records of a model, or sums a numeric field, grouped by a field (dates by day, week, "
		"month or year, e.g. date:month). For reports.")
	category = "analyze"
	schema = strict_object({
		"model": MODEL,
		"filters": FILTER_SCHEMA,
		"group_by": {"type": "array", "maxItems": 2, "items": {"type": "string", "maxLength": 64}},
		"sum": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 64}},
		"limit": {"type": "integer", "minimum": 1, "maximum": 100},
	}, ["model"])

	def plan(self, ctx, args):
		return Plan(summary=ctx.env._("Totals of %s", args["model"]), model=args["model"])

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, args["model"])
		domain &= filters_domain(ctx, args["model"], args.get("filters"))
		readable = set(ctx.fields(args["model"]))
		groupby = []
		for spec in args.get("group_by") or []:
			field_name, _sep, granularity = spec.partition(":")
			if field_name not in readable or not model._fields[field_name].store:
				raise ToolDenied(ctx.env._("The agent may not group by %s.", field_name))
			if granularity and granularity not in ("day", "week", "month", "quarter", "year"):
				raise ToolDenied(ctx.env._("Dates group by day, week, month, quarter or year."))
			groupby.append(spec)
		aggregates = ["__count"]
		for field_name in args.get("sum") or []:
			field = model._fields.get(field_name)
			if field_name not in readable or not field or field.type not in ("integer", "float", "monetary") or not field.store:
				raise ToolDenied(ctx.env._("The agent may not sum %s.", field_name))
			aggregates.append(f"{field_name}:sum")
		rows = model._read_group(domain, groupby, aggregates, limit=args.get("limit") or 50)
		result = []
		for row in rows:
			item = {}
			for spec, value in zip(groupby, row[:len(groupby)]):
				item[spec] = value.display_name if hasattr(value, "_name") else (str(value) if value else None)
			for spec, value in zip(aggregates, row[len(groupby):]):
				item["count" if spec == "__count" else spec.split(":")[0]] = round(value or 0, 2) if isinstance(value, float) else value
			result.append(item)
		return {"model": args["model"], "groups": result}
