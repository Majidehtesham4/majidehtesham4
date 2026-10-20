import frappe
from frappe import _
from frappe.utils import flt

from iran_erp.ai import tools
from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands import entities
from iran_erp.commands.engine import NeedSlot
from iran_erp.commands.handlers import (
	company,
	doc_link,
	jdate,
	link,
	money,
	number,
	period_or,
	report_url,
	require,
	table,
)


def _warehouses():
	return frappe.get_list("Warehouse", filters={"company": company(), "is_group": 0}, pluck="name")


def _default_warehouse():
	the_company = company()
	return (
		frappe.db.get_single_value("Stock Settings", "default_warehouse")
		or frappe.db.get_value(
			"Warehouse", {"company": the_company, "warehouse_name": "Stores", "is_group": 0}
		)
		or frappe.db.get_value("Warehouse", {"company": the_company, "is_group": 0})
	)


def stock_balance(context):
	require("Bin")
	item = context.get("item")
	warehouse = context.get("warehouse")
	if item:
		filters = {"item_code": item, "warehouse": ["in", [warehouse] if warehouse else _warehouses()]}
		rows = frappe.get_list(
			"Bin", filters=filters, fields=["warehouse", "actual_qty", "reserved_qty", "projected_qty"]
		)
		item_name, uom = frappe.db.get_value("Item", item, ["item_name", "stock_uom"])
		rows = [r for r in rows if r.actual_qty or r.reserved_qty or r.projected_qty]
		if not rows:
			return {
				"answer": _("{0} is not in stock.").format(item_name),
				"actions": [link(_("Open"), get_url_to_form("Item", item))],
			}
		total_qty = sum(flt(r.actual_qty) for r in rows)
		answer = _("Stock of {0}: {1} {2}").format(item_name, number(total_qty), _(uom))
		answer += "\n\n" + table(
			[_("Warehouse"), _("In stock"), _("Reserved"), _("Projected")],
			[
				[
					r.warehouse.rsplit(" - ", 1)[0],
					number(r.actual_qty),
					number(r.reserved_qty),
					number(r.projected_qty),
				]
				for r in rows
			],
		)
		return {
			"answer": answer,
			"actions": [
				link(_("Stock Ledger"), report_url("Stock Ledger", {"company": company(), "item_code": item}))
			],
		}
	if warehouse:
		rows = frappe.get_list(
			"Bin",
			filters={"warehouse": warehouse, "actual_qty": ["!=", 0]},
			fields=["item_code", "actual_qty", "stock_value"],
			order_by="stock_value desc",
			limit=15,
		)
		if not rows:
			return _("Warehouse {0} is empty.").format(warehouse)
		names = dict(
			frappe.get_all(
				"Item",
				filters={"name": ["in", [r.item_code for r in rows]]},
				fields=["name", "item_name"],
				as_list=True,
			)
		)
		return {
			"answer": f"**{warehouse}**\n\n"
			+ table(
				[_("Item"), _("Quantity"), _("Value")],
				[
					[names.get(r.item_code, r.item_code), number(r.actual_qty), money(r.stock_value)]
					for r in rows
				],
			),
			"actions": [
				link(
					_("Stock Balance"),
					report_url("Stock Balance", {"company": company(), "warehouse": warehouse}),
				)
			],
		}
	return _all_stock(context)


def _all_stock(context):
	"""Nothing named: the cars in the lot for a dealership, else every warehouse's stock."""
	from iran_erp.commands.handlers.insight import car_stock, has_cars

	words = set(context.message.words)
	if has_cars() and (words & {"خودرو", "خودروها", "ماشین", "ماشینها", "ماشین‌ها"} or not frappe.db.count("Bin", {"actual_qty": ["!=", 0]})):
		return car_stock(context)
	rows = frappe.get_list(
		"Bin",
		filters={"actual_qty": ["!=", 0], "warehouse": ["in", _warehouses()]},
		fields=["item_code", {"SUM": "actual_qty", "as": "qty"}, {"SUM": "stock_value", "as": "value"}],
		group_by="item_code",
		order_by="value desc",
		limit=15,
	)
	url = report_url("Stock Balance", {"company": company()})
	if not rows:
		return {"answer": _("Nothing is in stock in any warehouse."), "actions": [link(_("Stock Balance"), url)]}
	names = dict(
		frappe.get_all("Item", filters={"name": ["in", [r.item_code for r in rows]]}, fields=["name", "item_name"], as_list=True)
	)
	return {
		"answer": _("Stock in every warehouse (no item or warehouse was named); the most valuable first:")
		+ "\n\n"
		+ table(
			[_("Item"), _("Quantity"), _("Value")],
			[[names.get(r.item_code, r.item_code), number(r.qty), money(r.value)] for r in rows],
		),
		"actions": [link(_("Stock Balance"), url)],
	}


def stock_value(context):
	require("Bin")
	rows = frappe.get_list(
		"Bin",
		filters={"warehouse": ["in", _warehouses()]},
		fields=["warehouse", {"SUM": "stock_value", "as": "value"}],
		group_by="warehouse",
	)
	rows = [r for r in rows if flt(r.value)]
	total_value = sum(flt(r.value) for r in rows)
	answer = _("Stock is worth {0}.").format(money(total_value))
	if len(rows) > 1:
		answer += "\n\n" + table(
			[_("Warehouse"), _("Value")], [[r.warehouse.rsplit(" - ", 1)[0], money(r.value)] for r in rows]
		)
	return {
		"answer": answer,
		"actions": [link(_("Stock Balance"), report_url("Stock Balance", {"company": company()}))],
	}


def low_stock(context):
	require("Bin")
	warehouses = _warehouses()
	if not warehouses:
		return _("No warehouses found.")
	# Per item over all warehouses: projected stock at or under the reorder levels (or zero when none is set)
	rows = frappe.db.sql(
		"""select bin.item_code, item.item_name, sum(bin.actual_qty) actual_qty, sum(bin.projected_qty) projected_qty,
			(select ifnull(sum(reorder.warehouse_reorder_level), 0) from `tabItem Reorder` reorder
				where reorder.parent = bin.item_code and reorder.warehouse in %(warehouses)s) reorder_level
		from `tabBin` bin
		join `tabItem` item on item.name = bin.item_code and item.disabled = 0 and item.is_stock_item = 1
		where bin.warehouse in %(warehouses)s
		group by bin.item_code, item.item_name
		having projected_qty <= reorder_level
		order by projected_qty asc limit 20""",
		{"warehouses": warehouses},
		as_dict=True,
	)
	if not rows:
		return _("No item is running low.")
	return {
		"answer": f"**{_('Items running low')}**\n\n"
		+ table(
			[_("Item"), _("In stock"), _("Projected"), _("Reorder level")],
			[
				[r.item_name, number(r.actual_qty), number(r.projected_qty), number(r.reorder_level)]
				for r in rows
			],
		),
		"actions": [
			link(_("Stock Projected Qty"), report_url("Stock Projected Qty", {"company": company()}))
		],
	}


def item_info(context):
	item = context.get("item")
	require("Item")
	doc = frappe.get_doc("Item", item)
	lines = [f"**{doc.item_name}**", ""]
	for label, value in (
		(_("Item Code"), doc.item_code),
		(_("Item Group"), _(doc.item_group)),
		(_("Unit"), _(doc.stock_uom)),
		(_("Type"), _("Stock item") if doc.is_stock_item else _("Service / non-stock")),
		(_("Product/Service ID (Moadian)"), doc.get("iran_sstid")),
		(
			_("Description"),
			frappe.utils.strip_html(doc.description or "")[:200] if doc.description != doc.item_name else "",
		),
	):
		if value:
			lines.append(f"- {label}: {value}")
	return {"answer": "\n".join(lines), "actions": [link(_("Open"), get_url_to_form("Item", item))]}


def create_item(context):
	name = context.get("name")
	price = context.get("amount")
	service = any(w in ("خدمت", "خدمات", "سرویس") for w in context.message.words)
	result = tools.create_items(
		[{"item_name": name, "selling_price": price, "is_service": service}], company()
	)
	entities.forget("item")
	if result.get("items_already_existing"):
		code = result["items_already_existing"][0]
		return {
			"answer": _("{0} is already defined.").format(name),
			"actions": [link(_("Open"), get_url_to_form("Item", code))],
		}
	code = result["items_created"][0]
	answer = _("Item {0} was created.").format(name)
	if price:
		answer += " " + _("Selling price: {0}").format(money(price))
	return {"answer": answer, "actions": [doc_link("Item", code)]}


def _stock_entry(context, entry_type, source=None, target=None):
	require("Stock Entry", "create")
	lines = (context.get("items") or {}).get("lines") or []
	rows = []
	for line in lines:
		row = {"item_code": line["item"], "qty": flt(line.get("qty")) or 1}
		if source:
			row["s_warehouse"] = source
		if target:
			row["t_warehouse"] = target
		if line.get("rate"):
			row["basic_rate"] = line["rate"]
		rows.append(row)
	doc = frappe.get_doc(
		{"doctype": "Stock Entry", "stock_entry_type": entry_type, "company": company(), "items": rows}
	).insert()
	listing = "\n".join(f"- {r.item_name}: {number(r.qty)}" for r in doc.items)
	return doc, listing


def stock_receipt(context):
	warehouse = context.get("warehouse") or _default_warehouse()
	doc, listing = _stock_entry(context, "Material Receipt", target=warehouse)
	return {
		"answer": _("Draft stock receipt into {0}:").format(warehouse)
		+ "\n"
		+ listing
		+ "\n\n"
		+ _("Stock changes when you submit it."),
		"actions": [doc_link("Stock Entry", doc.name)],
	}


def stock_issue(context):
	warehouse = context.get("warehouse") or _default_warehouse()
	doc, listing = _stock_entry(context, "Material Issue", source=warehouse)
	return {
		"answer": _("Draft stock issue from {0}:").format(warehouse)
		+ "\n"
		+ listing
		+ "\n\n"
		+ _("Stock changes when you submit it."),
		"actions": [doc_link("Stock Entry", doc.name)],
	}


def stock_transfer(context):
	message = context.message
	found = []
	skip = set(message.used)
	for _attempt in range(2):
		match = entities.find("warehouse", message.words, skip)
		if not match:
			break
		start = min(match.used)
		found.append((start, match.name))
		skip |= match.used
	source = target = None
	for start, name in found:
		before = message.words[start - 1] if start else ""
		if before == "از":
			source = name
		elif before in ("به", "تو", "توی", "انبار") and not target:
			target = name
	if len(found) == 2 and not (source and target):
		names = [name for _start, name in sorted(found)]
		source, target = source or names[0], target or names[1]
	if not target:
		raise NeedSlot("items", _("Move to which warehouse? Write: from <warehouse> to <warehouse>."))
	source = source or _default_warehouse()
	doc, listing = _stock_entry(context, "Material Transfer", source=source, target=target)
	return {
		"answer": _("Draft transfer from {0} to {1}:").format(source, target) + "\n" + listing,
		"actions": [doc_link("Stock Entry", doc.name)],
	}


def item_movements(context):
	require("Stock Ledger Entry")
	item = context.get("item")
	start, end, label = period_or(context, "year")
	rows = frappe.get_list(
		"Stock Ledger Entry",
		filters={
			"item_code": item,
			"is_cancelled": 0,
			"company": company(),
			"posting_date": ["between", [start, end]],
		},
		fields=[
			"posting_date",
			"voucher_type",
			"voucher_no",
			"warehouse",
			"actual_qty",
			"qty_after_transaction",
		],
		order_by="posting_date desc, creation desc",
		limit=15,
	)
	item_name = frappe.db.get_value("Item", item, "item_name")
	url = report_url(
		"Stock Ledger", {"company": company(), "item_code": item, "from_date": start, "to_date": end}
	)
	if not rows:
		return {
			"answer": _("No movements of {0} in {1}.").format(item_name, label),
			"actions": [link(_("Stock Ledger"), url)],
		}
	answer = f"**{_('Movements of {0}').format(item_name)}** ({label})\n\n" + table(
		[_("Date"), _("Document"), _("Warehouse"), _("In/Out"), _("Balance")],
		[
			[
				jdate(r.posting_date),
				f"[{r.voucher_no}]({get_url_to_form(r.voucher_type, r.voucher_no)})",
				r.warehouse.rsplit(" - ", 1)[0],
				number(r.actual_qty),
				number(r.qty_after_transaction),
			]
			for r in rows
		],
	)
	return {"answer": answer, "actions": [link(_("Stock Ledger"), url)]}
