import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

from iran_erp.ai import tools
from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands import entities
from iran_erp.commands.engine import NeedConfirm, NeedSlot, Reroute
from iran_erp.commands.handlers import (
	company,
	count,
	doc_link,
	document_list,
	jdate,
	link,
	list_url,
	money,
	number,
	party_label,
	party_of,
	period_or,
	report_url,
	require,
	table,
)

SELLING_PRICE_LIST = "Standard Selling"
BUYING_PRICE_LIST = "Standard Buying"


def _invoice_filters(context, party_field="customer", default="month"):
	start, end, label = period_or(context, default)
	filters = {"docstatus": 1, "company": company(), "posting_date": ["between", [start, end]]}
	party = context.get(party_field)
	if party:
		filters[party_field] = party
	return filters, label


def _totals(doctype, filters):
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=[
			{"COUNT": "name", "as": "n"},
			{"SUM": "base_net_total", "as": "net"},
			{"SUM": "base_grand_total", "as": "gross"},
		],
	)
	return rows[0] if rows else frappe._dict(n=0, net=0, gross=0)


def sales_total(context):
	require("Sales Invoice")
	from iran_erp.commands.query import shape

	# «فروش هر شعبه», «به تفکیک شعبه»: one line per branch
	if shape(context.message.text).get("group_by") == "branch":
		raise Reroute("sales_by_branch")
	filters, label = _invoice_filters(context)
	row = _totals("Sales Invoice", filters)
	who = f" {_('to')} {party_label('Customer', filters['customer'])}" if filters.get("customer") else ""
	if not row.n:
		return _("No sales{0} in {1}.").format(who, label)
	answer = _("Sales{0} in {1}: {2} invoices, {3} before tax, {4} with tax.").format(
		who, label, number(row.n), money(row.net), money(row.gross)
	)
	return {"answer": answer, "actions": [link(_("Open the invoices"), list_url("Sales Invoice", filters))]}


def _top(doctype, party_field, label_field, context, title):
	require(doctype)
	filters, label = _invoice_filters(context, party_field="", default="year")
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=[
			party_field,
			label_field,
			{"SUM": "base_net_total", "as": "total"},
			{"COUNT": "name", "as": "n"},
		],
		group_by=party_field,
	)
	rows = sorted(rows, key=lambda r: flt(r.total), reverse=True)[: context.get("limit", 10)]
	if not rows:
		return _("Nothing in {0}.").format(label)
	return f"**{title}** ({label})\n\n" + table(
		["#", _("Name"), _("Invoices"), _("Amount")],
		[
			[number(i), r.get(label_field) or r.get(party_field), number(r.n), money(r.total)]
			for i, r in enumerate(rows, 1)
		],
	)


def top_customers(context):
	return _top("Sales Invoice", "customer", "customer_name", context, _("Top customers"))


def _item_rows(start, end, item=None):
	require("Sales Invoice")
	condition = "and item.item_code = %(item)s" if item else ""
	return frappe.db.sql(
		f"""select item.item_code, item.item_name, sum(item.stock_qty) qty, sum(item.base_net_amount) amount
		from `tabSales Invoice Item` item join `tabSales Invoice` inv on inv.name = item.parent
		where inv.docstatus=1 and inv.company=%(company)s and inv.posting_date between %(start)s and %(end)s {condition}
		group by item.item_code, item.item_name order by amount desc""",
		{"company": company(), "start": start, "end": end, "item": item},
		as_dict=True,
	)


def top_items(context):
	start, end, label = period_or(context, "year")
	rows = _item_rows(start, end)
	ascending = any(w.startswith("کم") for w in context.message.words)
	if ascending:
		rows = list(reversed(rows))
	rows = rows[: context.get("limit", 10)]
	if not rows:
		return _("No sales in {0}.").format(label)
	title = _("Least sold items") if ascending else _("Best selling items")
	return f"**{title}** ({label})\n\n" + table(
		["#", _("Item"), _("Quantity"), _("Amount")],
		[[number(i), r.item_name, number(r.qty), money(r.amount)] for i, r in enumerate(rows, 1)],
	)


def item_sales(context):
	start, end, label = period_or(context, "year")
	item = context.get("item")
	rows = _item_rows(start, end, item)
	name = frappe.db.get_value("Item", item, "item_name")
	if not rows:
		return _("{0} was not sold in {1}.").format(name, label)
	return _("{0} in {1}: {2} sold, for {3} before tax.").format(
		name, label, number(rows[0].qty), money(rows[0].amount)
	)


def last_sales_invoices(context):
	filters = {"company": company(), "docstatus": ["<", 2]}
	if context.get("customer"):
		filters["customer"] = context.get("customer")
	if context.get("period"):
		filters["posting_date"] = ["between", [context.get("period")["from"], context.get("period")["to"]]]
	return document_list(
		"Sales Invoice",
		filters,
		[
			("name", _("Invoice"), "link"),
			("customer_name", _("Customer"), ""),
			("posting_date", _("Date"), "date"),
			("grand_total", _("Total"), "money"),
			("status", _("Status"), "status"),
		],
		_("Latest sales invoices"),
		limit=500 if context.get("output") == "all" else context.get("limit", 10),
		exclude=context.get("_exclude"),
	)


def invoice_info(context):
	doctype, _sep, name = context.get("document").partition(":")
	if not frappe.has_permission(doctype, "read", name):
		raise frappe.PermissionError
	doc = frappe.get_doc(doctype, name)
	party = doc.get("customer_name") or doc.get("supplier_name") or doc.get("party_name") or ""
	lines = [f"**{_(doctype)} {doc.name}** — {party}", ""]
	for label, value in (
		(_("Date"), jdate(doc.get("posting_date") or doc.get("transaction_date"))),
		(_("Status"), _(doc.get("status") or "")),
		(_("Total"), money(doc.get("grand_total")) if doc.get("grand_total") is not None else ""),
		(_("Outstanding"), money(doc.get("outstanding_amount")) if doc.get("outstanding_amount") else ""),
		(_("Due Date"), jdate(doc.get("due_date"))),
	):
		if value:
			lines.append(f"- {label}: {value}")
	if doc.get("items"):
		lines.append("")
		lines.append(
			table(
				[_("Item"), _("Quantity"), _("Rate"), _("Amount")],
				[[r.item_name, number(r.qty), money(r.rate), money(r.amount)] for r in doc.items[:15]],
			)
		)
	return {"answer": "\n".join(lines), "actions": [link(_("Open"), get_url_to_form(doctype, name))]}


def _price(item_code, price_list=SELLING_PRICE_LIST):
	return flt(
		frappe.db.get_value(
			"Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate"
		)
	)


def _lines(context, price_list=SELLING_PRICE_LIST):
	lines = (context.get("items") or {}).get("lines") or []
	return [
		{
			"item_code": line["item"],
			"qty": flt(line.get("qty")) or 1,
			"rate": flt(line.get("rate")) or _price(line["item"], price_list),
		}
		for line in lines
	]


def _vat_template(doctype, the_company):
	return frappe.db.get_value(doctype, {"company": the_company, "is_default": 1, "disabled": 0})


def _summary(doc):
	rows = [[r.item_name, number(r.qty), money(r.rate), money(r.amount)] for r in doc.items]
	text = table([_("Item"), _("Quantity"), _("Rate"), _("Amount")], rows)
	text += "\n\n" + _("Total: {0}").format(money(doc.grand_total))
	if doc.get("total_taxes_and_charges"):
		text += " (" + _("including {0} tax").format(money(doc.total_taxes_and_charges)) + ")"
	if any(not r.rate for r in doc.items):
		text += "\n\n⚠️ " + _("Some lines have no price; set it in the draft.")
	return text


def create_sales_invoice(context):
	the_company = company()
	template = _vat_template("Sales Taxes and Charges Template", the_company)
	vat = context.get("vat")
	if template and vat is None:
		raise NeedSlot("vat", _("Add value added tax to this invoice? (yes / no)"))
	result = tools.create_sales_invoice_draft(
		customer=context.get("customer"),
		items=_lines(context),
		discount_percentage=context.get("percent"),
		apply_vat=vat == "yes",
		company=the_company,
	)
	if result.get("error"):
		frappe.throw(result["error"])
	doc = frappe.get_doc("Sales Invoice", result["name"])
	return {
		"answer": _("Draft sales invoice for {0}:").format(doc.customer_name) + "\n\n" + _summary(doc),
		"actions": [doc_link("Sales Invoice", doc.name)],
	}


def _selling_document(context, doctype, extra, line_extra=None):
	require(doctype, "create")
	the_company = company()
	items = [{**line, **(line_extra or {})} for line in _lines(context)]
	doc = frappe.get_doc({"doctype": doctype, "company": the_company, "items": items, **extra})
	template = _vat_template("Sales Taxes and Charges Template", the_company)
	if template and doctype == "Quotation":
		doc.taxes_and_charges = template
		doc.append_taxes_from_master()
	doc.insert()
	return doc


def create_quotation(context):
	customer = context.get("customer")
	doc = _selling_document(
		context,
		"Quotation",
		{
			"quotation_to": "Customer",
			"party_name": customer,
			"transaction_date": nowdate(),
			"valid_till": add_days(nowdate(), 15),
		},
	)
	return {
		"answer": _("Draft quotation for {0}:").format(party_label("Customer", customer))
		+ "\n\n"
		+ _summary(doc),
		"actions": [doc_link("Quotation", doc.name)],
	}


def create_sales_order(context):
	customer = context.get("customer")
	delivery = context.get("date") or add_days(nowdate(), 7)
	doc = _selling_document(
		context,
		"Sales Order",
		{"customer": customer, "transaction_date": nowdate(), "delivery_date": delivery},
		{"delivery_date": delivery},
	)
	return {
		"answer": _("Draft sales order for {0}, delivery {1}:").format(
			party_label("Customer", customer), jdate(delivery)
		)
		+ "\n\n"
		+ _summary(doc),
		"actions": [doc_link("Sales Order", doc.name)],
	}


def pending_sales_orders(context):
	filters = {
		"docstatus": 1,
		"company": company(),
		"status": ["in", ["To Deliver and Bill", "To Deliver", "To Bill"]],
	}
	if context.get("customer"):
		filters["customer"] = context.get("customer")
	return document_list(
		"Sales Order",
		filters,
		[
			("name", _("Order"), "link"),
			("customer_name", _("Customer"), ""),
			("delivery_date", _("Delivery Date"), "date"),
			("grand_total", _("Total"), "money"),
			("status", _("Status"), "status"),
		],
		_("Open sales orders"),
		order_by="delivery_date asc",
		empty=_("Every sales order is delivered and billed."),
	)


def open_quotations(context):
	filters = {"docstatus": 1, "company": company(), "status": ["in", ["Open", "Replied", "Expired"]]}
	if context.get("customer"):
		filters["party_name"] = context.get("customer")
	return document_list(
		"Quotation",
		filters,
		[
			("name", _("Quotation"), "link"),
			("customer_name", _("Customer"), ""),
			("valid_till", _("Valid Till"), "date"),
			("grand_total", _("Total"), "money"),
			("status", _("Status"), "status"),
		],
		_("Open quotations"),
		order_by="valid_till asc",
		empty=_("No open quotations."),
	)


def unbilled_deliveries(context):
	return document_list(
		"Delivery Note",
		{"docstatus": 1, "company": company(), "status": "To Bill"},
		[
			("name", _("Delivery Note"), "link"),
			("customer_name", _("Customer"), ""),
			("posting_date", _("Date"), "date"),
			("grand_total", _("Total"), "money"),
		],
		_("Delivery notes not billed yet"),
		empty=_("Every delivery note is billed."),
	)


def sales_returns(context):
	start, end, label = period_or(context, "year")
	return document_list(
		"Sales Invoice",
		{"docstatus": 1, "is_return": 1, "company": company(), "posting_date": ["between", [start, end]]},
		[
			("name", _("Invoice"), "link"),
			("customer_name", _("Customer"), ""),
			("posting_date", _("Date"), "date"),
			("grand_total", _("Total"), "money"),
		],
		_("Sales returns") + f" ({label})",
		empty=_("No sales returns in {0}.").format(label),
	)


def create_customer(context):
	result = tools.create_customer(
		customer_name=context.get("name"), city=context.get("city"), mobile=context.get("mobile")
	)
	if result.get("error"):
		raise NeedSlot(
			"mobile",
			_("The mobile number is not valid. Write an 11 digit number starting with 09, or «none»."),
		)
	entities.forget("customer")
	if result.get("already_existed"):
		return {
			"answer": _("{0} is already a customer.").format(context.get("name")),
			"actions": [link(_("Open"), get_url_to_form("Customer", result["customer"]))],
		}
	return {
		"answer": _("Customer {0} was created.").format(context.get("name")),
		"actions": [doc_link("Customer", result["name"])],
	}


def party_info(context):
	doctype, name = party_of(context.get("party"))
	require(doctype)
	doc = frappe.get_doc(doctype, name)
	lines = [f"**{party_label(doctype, name)}** ({_(doctype)})", ""]
	address = (
		frappe.db.get_value(
			"Address", doc.get(f"{doctype.lower()}_primary_address"), ["address_line1", "city"], as_dict=True
		)
		if doc.get(f"{doctype.lower()}_primary_address")
		else None
	)
	invoice_doctype = "Sales Invoice" if doctype == "Customer" else "Purchase Invoice"
	last = frappe.get_list(
		invoice_doctype,
		filters={doctype.lower(): name, "docstatus": 1},
		fields=["posting_date", "grand_total"],
		order_by="posting_date desc",
		limit=1,
	)
	for label, value in (
		(_("Mobile"), doc.get("mobile_no")),
		(_("Email"), doc.get("email_id")),
		(
			_("Address"),
			" - ".join(filter(None, [address.address_line1, address.city]))
			if address
			else doc.get("primary_address"),
		),
		(_("Economic Code"), doc.get("iran_economic_code")),
		(_("National ID"), doc.get("iran_national_id")),
		(_("Group"), doc.get("customer_group") or doc.get("supplier_group")),
		(_("Last invoice"), f"{jdate(last[0].posting_date)} — {money(last[0].grand_total)}" if last else ""),
	):
		if value:
			lines.append(f"- {label}: {value}")
	if len(lines) == 2:
		lines.append(_("No contact details are recorded."))
	return {"answer": "\n".join(lines), "actions": [link(_("Open"), get_url_to_form(doctype, name))]}


def customer_count(context):
	require("Customer")
	total_count = count("Customer", {"disabled": 0})
	start, end, label = period_or(context)
	new = count("Customer", {"disabled": 0, "creation": ["between", [start, f"{end} 23:59:59"]]})
	return _("{0} customers in total; {1} new in {2}.").format(number(total_count), number(new), label)


def item_price(context):
	item = context.get("item")
	require("Item")
	row = frappe.db.get_value(
		"Item", item, ["item_name", "last_purchase_rate", "valuation_rate", "stock_uom"], as_dict=True
	)
	lines = [f"**{row.item_name}**", ""]
	selling = _price(item, SELLING_PRICE_LIST)
	buying = _price(item, BUYING_PRICE_LIST)
	lines.append(f"- {_('Selling price')}: {money(selling) if selling else _('not set')}")
	if frappe.has_permission("Purchase Invoice", "read"):
		if buying:
			lines.append(f"- {_('Buying price list')}: {money(buying)}")
		if row.last_purchase_rate:
			lines.append(f"- {_('Last purchase price')}: {money(row.last_purchase_rate)}")
		if row.valuation_rate:
			lines.append(f"- {_('Average cost')}: {money(row.valuation_rate)}")
	return {"answer": "\n".join(lines), "actions": [link(_("Open"), get_url_to_form("Item", item))]}


def set_item_price(context):
	item = context.get("item")
	price = flt(context.get("amount"))
	require("Item Price", "write")
	name = frappe.db.get_value("Item Price", {"item_code": item, "price_list": SELLING_PRICE_LIST})
	old = _price(item)
	item_name = frappe.db.get_value("Item", item, "item_name")
	if not context.confirmed:
		raise NeedConfirm(
			_("Change the selling price of {0} from {1} to {2}").format(
				item_name, money(old) if old else _("not set"), money(price)
			)
		)
	if name:
		doc = frappe.get_doc("Item Price", name)
		doc.price_list_rate = price
		doc.save()
	else:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item,
				"price_list": SELLING_PRICE_LIST,
				"price_list_rate": price,
			}
		).insert()
	return {
		"answer": _("The selling price of {0} is now {1}.").format(item_name, money(price)),
		"actions": [link(_("Open"), get_url_to_form("Item", item))],
	}


def sales_by_branch(context):
	"""Sales of each branch in a period: submitted sales invoices, and the dealership's instalment
	sale contracts, by the branch recorded on them. With no period said, this Solar Hijri year."""
	require("Sales Invoice")
	start, end, label = period_or(context, "year")
	context.values["group_by"] = "branch"
	said_period = bool(context.get("period"))
	invoice_filters = {"docstatus": 1, "company": company(), "posting_date": ["between", [start, end]]}
	rows = {}

	def add(branch, **values):
		row = rows.setdefault(branch or "", frappe._dict(invoices=0, invoiced=0.0, contracts=0, contracted=0.0))
		for key, value in values.items():
			row[key] += value or 0

	for r in frappe.get_list(
		"Sales Invoice",
		filters=invoice_filters,
		fields=["branch", {"COUNT": "name", "as": "n"}, {"SUM": "base_net_total", "as": "total"}],
		group_by="branch",
	):
		add(r.branch, invoices=r.n, invoiced=flt(r.total))
	contract_filters = {"docstatus": 1, "status": ["!=", "Cancelled"], "posting_date": ["between", [start, end]]}
	if frappe.db.exists("DocType", "Iran Instalment Sale") and frappe.has_permission("Iran Instalment Sale", "read"):
		for r in frappe.get_list(
			"Iran Instalment Sale",
			filters=contract_filters,
			fields=["branch", {"COUNT": "name", "as": "n"}, {"SUM": "sale_price", "as": "total"}],
			group_by="branch",
		):
			add(r.branch, contracts=r.n, contracted=flt(r.total))
	# Branches with no sales are shown too, so «nothing» is seen, not missed
	for branch in frappe.get_all("Branch", pluck="name"):
		rows.setdefault(branch, frappe._dict(invoices=0, invoiced=0.0, contracts=0, contracted=0.0))

	period_note = label if said_period else _("{0} (no period was said)").format(label)
	if not any(r.invoices or r.contracts for r in rows.values()):
		return {
			"answer": _("No sales in {0}, in any branch.").format(period_note),
			"actions": [link(_("Sales invoices"), list_url("Sales Invoice", invoice_filters))],
			"records": 0,
		}
	ordered = sorted(rows.items(), key=lambda kv: -(kv[1].invoiced + kv[1].contracted))

	def branch_link(branch):
		value = branch if branch else ["is", "not set"]
		return f"[{branch or _('No branch set')}]({list_url('Sales Invoice', {**invoice_filters, 'branch': value})})"

	lines = [f"**{_('Sales by branch')}** ({period_note})", ""]
	lines.append(
		table(
			[_("Branch"), _("Invoices"), _("Invoiced (before tax)"), _("Instalment sales"), _("Contract amounts"), _("Total")],
			[
				[branch_link(b), number(r.invoices), money(r.invoiced), number(r.contracts), money(r.contracted), money(r.invoiced + r.contracted)]
				for b, r in ordered
			],
		)
	)
	unassigned = rows.get("")
	if unassigned and (unassigned.invoices or unassigned.contracts):
		lines += ["", _("Sales with no branch on them are under «No branch set»; set the branch on the invoice to place them.")]
	return {
		"answer": "\n".join(lines),
		"actions": [
			link(
				_("Sales Register ({0})").format(label),
				report_url("Sales Register", {"company": company(), "from_date": start, "to_date": end}),
			),
			link(_("Instalment sales"), list_url("Iran Instalment Sale", contract_filters)),
		],
		"records": len(ordered),
	}
