"""Reading Odoo data: only models in the agent's data scope, only fields it may read, with the person's
own access rights and companies. No free query, no dotted path through relations, no write."""


from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Domain
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


MONEY_FIELDS = ("amount_total", "amount_residual", "amount", "amount_untaxed", "price_total", "balance", "expected_revenue",
	"list_price", "price")
DATE_FIELDS = ("date", "date_order", "invoice_date", "create_date", "date_deadline", "scheduled_date")


SKIPPED = ("message_", "activity_", "access_", "website_message", "has_message", "rating_", "my_activity", "is_follower",
	"_", "create_", "write_", "needed_terms", "tax_totals", "invoice_has", "show_", "display_", "duplicated_", "abnormal_",
	"hide_", "need_", "made_sequence", "sequence_", "highest_name", "auto_post", "quick_")
# What a person asks about a document first, when the model has it
FIRST = ("partner_id", "ref", "invoice_date", "date_order", "date", "invoice_date_due", "amount_untaxed", "amount_tax",
	"amount_total", "amount_residual", "state")
SKIPPED_NAMES = {"id", "display_name", "company_currency_id", "currency_id", "commercial_partner_id", "user_id_display"}


@tool
class PageOverview(Tool):
	code = "page_overview"
	name = _lt("Overview of a Section or a Record")
	description = _lt("For any section of the program: the number of records, how many are in each state, the totals of "
		"the main amounts and the newest records; or, with an id, the fields of one record with their names. Only what "
		"the person may see.")
	category = "read"
	schema = strict_object({"model": MODEL, "id": {"type": "integer", "minimum": 1}, "filters": FILTER_SCHEMA}, ["model"])

	def plan(self, ctx, args):
		return Plan(summary=ctx.env._("Overview of %s", args["model"]), model=args["model"])

	def _label(self, ctx, model, name):
		return model._fields[name]._description_string(ctx.env).strip().rstrip(":：").strip()

	def _important(self, model, names):
		"""The fields a person reads on the record first: what it is, who, how much, when and its state; not the
		program's own bookkeeping"""
		def rank(name):
			field = model._fields[name]
			return (not field.required, {"many2one": 0, "monetary": 1, "date": 2, "selection": 3, "char": 4}.get(field.type, 5))

		kept = [name for name in names if not name.startswith(SKIPPED) and name not in SKIPPED_NAMES
			and model._fields[name].type not in ("one2many", "html", "json", "properties", "binary")]
		first = [name for name in FIRST if name in kept]
		# Then the fields the record's form shows, in its order: not those always hidden, nor those of its lines
		shown = []
		try:
			root = etree.fromstring(model.get_view(view_type="form")["arch"])
			for node in root.iter("field"):
				if any(parent.tag == "field" for parent in node.iterancestors()):
					continue
				if (node.get("invisible") or "").strip() in ("1", "True", "true") or node.get("name") in shown:
					continue
				shown.append(node.get("name"))
		except Exception:  # noqa: BLE001 - a model without a form is ranked by its fields alone
			shown = []
		on_form = [name for name in shown if name in kept and name not in first]
		return (first + (on_form or sorted((n for n in kept if n not in first), key=rank)))[:25]

	def _record(self, ctx, model, record, names):
		values = {}
		for name in self._important(model, names):
			field = model._fields[name]
			if name in ("id", "display_name"):
				continue
			try:
				value = plain(record, [name]).get(name)
			except AccessError:
				# A related record the person may not see is left out, not the whole answer
				continue
			if field.type == "selection" and value:
				value = dict(field._description_selection(ctx.env)).get(value, value)
			if value not in (None, "", [], False):
				values[self._label(ctx, model, name)] = value
		return values

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, args["model"])
		readable = ctx.fields(args["model"])
		title = ctx.env["ir.model"]._get(args["model"]).name
		if args.get("id"):
			record = model.search(domain & Domain("id", "=", args["id"]), limit=1)
			if not record:
				raise ToolDenied(ctx.env._("No such record in the agent's data."))
			ctx.link(record)
			return {"title": record.display_name, "details": self._record(ctx, model, record, readable)}
		domain &= filters_domain(ctx, args["model"], args.get("filters"))
		result = {"section": title, "count": model.search_count(domain)}
		state = model._fields.get("state")
		if state and state.type == "selection" and state.store and "state" in readable:
			labels = dict(state._description_selection(ctx.env))
			result["by_state"] = [{"state": labels.get(value, value), "count": count}
				for value, count in model._read_group(domain, ["state"], ["__count"])]
		money = [name for name in MONEY_FIELDS if name in readable and model._fields[name].store
			and model._fields[name].type in ("monetary", "float")][:2]
		if money:
			totals = model._read_group(domain, [], [f"{name}:sum" for name in money])[0]
			result["totals"] = {self._label(ctx, model, name): round(value or 0, 2) for name, value in zip(money, totals)}
		date = next((name for name in DATE_FIELDS if name in readable and model._fields[name].store), None)
		newest = model.search(domain, limit=5, order=f"{date} desc, id desc" if date else "id desc")
		shown = [name for name in (date, *money) if name]
		result["newest"] = [{ctx.env._("Name"): record.display_name, **{self._label(ctx, model, name): plain(record, [name]).get(name)
			for name in shown}} for record in newest]
		ctx.link(newest)
		return result
