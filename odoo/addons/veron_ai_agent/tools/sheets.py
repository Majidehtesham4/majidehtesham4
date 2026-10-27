"""Spreadsheets given to a run: reading them, and adding the contacts or products they list"""

import re

from odoo.tools.translate import LazyTranslate

from ..services import nlu, sheets
from ..services.registry import Plan, Tool, ToolDenied, tool
from ..services.schema import strict_object

_lt = LazyTranslate(__name__)
SOURCE = {"source_id": {"type": "integer", "minimum": 1, "description": "A spreadsheet file of this run"},
	"sheet": {"type": "string", "maxLength": 100, "description": "The name of the sheet; the first by default"}}
# Columns of phones, codes and numbers are not added up
CODES = re.compile(r"تلفن|موبایل|همراه|کد|شناسه|شماره|phone|mobile|code|\bid\b|zip|vat", re.I)
# The columns a sheet may have for each kind of record, by the words of their header
COLUMNS = {
	"contacts": {
		"name": ("name", "نام", "نام و نام خانوادگی", "نام مشتری", "مشتری", "نام شخص", "شرکت", "نام شرکت"),
		"phone": ("phone", "تلفن", "شماره تلفن", "تلفن ثابت"),
		"mobile": ("mobile", "موبایل", "همراه", "تلفن همراه", "شماره موبایل"),
		"email": ("email", "ایمیل", "پست الکترونیک"),
		"city": ("city", "شهر"),
		"street": ("address", "street", "نشانی", "آدرس"),
		"vat": ("vat", "کد اقتصادی", "شناسه ملی", "کد ملی"),
	},
	"products": {
		"name": ("name", "نام", "نام کالا", "کالا", "محصول", "نام محصول", "شرح"),
		"default_code": ("code", "default_code", "کد", "کد کالا", "کد محصول"),
		"barcode": ("barcode", "بارکد"),
		"list_price": ("price", "list_price", "قیمت", "قیمت فروش", "فی فروش"),
		"standard_price": ("cost", "standard_price", "قیمت خرید", "بهای تمام شده", "فی خرید"),
	},
}
MODELS = {"contacts": "res.partner", "products": "product.template"}


def _sheet(ctx, args):
	source = ctx.sources([args["source_id"]])
	if not source or source.kind != "sheet":
		raise ToolDenied(ctx.env._("The file is not a spreadsheet of this run."))
	books = sheets.read(source._data(), source.mimetype)
	name = args.get("sheet") or next(iter(books), "")
	if name not in books:
		raise ToolDenied(ctx.env._("The file has no sheet named %(name)s; it has: %(names)s", name=name,
			names=", ".join(books)))
	return source, list(books), name, books[name]


def _mapping(header, target):
	columns = {}
	for field, words in COLUMNS[target].items():
		wanted = {nlu.normalize(word) for word in words}
		for column in header:
			if nlu.normalize(column) in wanted and field not in columns:
				columns[field] = column
	return columns


@tool
class SpreadsheetRead(Tool):
	code = "spreadsheet_read"
	name = _lt("Read a Spreadsheet")
	description = _lt("Reads an Excel (xlsx) or CSV file given to this run: its sheets, the columns of the first row, the "
		"number of rows, the first rows and the totals of the numeric columns.")
	category = "read"
	schema = strict_object({**SOURCE, "rows": {"type": "integer", "minimum": 1, "maximum": 50}}, ["source_id"])

	def plan(self, ctx, args):
		return Plan(summary=ctx.env._("Read the spreadsheet"))

	def execute(self, ctx, args, plan):
		source, names, name, rows = _sheet(ctx, args)
		header, records = sheets.table(rows)
		totals = {}
		for column in header:
			if CODES.search(column):
				continue
			values = [record.get(column) for record in records]
			numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
			if numbers and len(numbers) >= len([v for v in values if v not in ("", None)]) * 0.8:
				totals[column] = round(sum(numbers), 2)
		return {"file": source.name, "sheets": names, "sheet": name, "columns": header, "rows": len(records),
			"first_rows": records[:args.get("rows") or 10], "totals": totals}


@tool
class RecordsImport(Tool):
	code = "records_import"
	name = _lt("Add Contacts or Products From a Spreadsheet")
	description = _lt("Adds the contacts or the products a spreadsheet lists, by the names of its columns (name, phone, "
		"email, city, code, barcode, price...). Those already there by name or code are skipped. It waits for approval.")
	category = "execute"
	action = "execute"
	risk = "medium"
	models = ("res.partner", "product.template")
	schema = strict_object({**SOURCE, "target": {"type": "string", "enum": ["contacts", "products"]}},
		["source_id", "target"])

	def _rows(self, ctx, args):
		model = MODELS[args["target"]]
		ctx.check_model(model)
		source, _names, _name, rows = _sheet(ctx, args)
		header, records = sheets.table(rows)
		columns = _mapping(header, args["target"])
		if "name" not in columns:
			raise ToolDenied(ctx.env._("No column of the names was found; name it «نام»."))
		Model = ctx.env[model]
		new, existing = [], []
		seen = set()
		for record in records[:1000]:
			values = {field: record.get(column) for field, column in columns.items() if record.get(column) not in ("", None)}
			name = str(values.get("name") or "").strip()
			if not name or nlu.normalize(name) in seen:
				continue
			seen.add(nlu.normalize(name))
			values["name"] = name
			domain = [("name", "=ilike", name)]
			if values.get("default_code"):
				values["default_code"] = str(values["default_code"])
				domain = ["|", ("default_code", "=", values["default_code"])] + domain
			if Model.search_count(domain, limit=1):
				existing.append(name)
				continue
			for field in ("phone", "mobile", "vat", "barcode"):
				if field in values:
					values[field] = str(values[field])
			if "mobile" in values and "mobile" not in Model._fields:
				values["phone"] = values.pop("mobile") if not values.get("phone") else values.get("phone")
				values.pop("mobile", None)
			new.append(values)
		return model, columns, new, existing

	def plan(self, ctx, args):
		model, columns, new, existing = self._rows(ctx, args)
		kind = ctx.env._("contacts") if args["target"] == "contacts" else ctx.env._("products")
		return Plan(summary=ctx.env._("Add %(count)s %(kind)s from the spreadsheet (%(existing)s already there are skipped)",
			count=len(new), kind=kind, existing=len(existing)), model=model, company_ids=[ctx.env.company.id],
			data={"columns": columns})

	def execute(self, ctx, args, plan):
		model, columns, new, existing = self._rows(ctx, args)
		records = ctx.env[model].create(new) if new else ctx.env[model]
		ctx.link(records[:20])
		return {"created": len(records), "skipped": len(existing), "columns": columns,
			"names": records[:20].mapped("display_name"), "already_there": existing[:20]}
