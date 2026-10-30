"""Finance tools of the agents. They read posted accounting with the person's own rights and the agent's
data scope; the only one that writes makes a draft invoice, which a person checks and posts."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.veron_ai_agent.services.registry import Plan, Tool, ToolDenied, tool
from odoo.addons.veron_ai_agent.services.schema import strict_object
from odoo.addons.veron_ai_agent.tools.common import PERIOD, period, scoped
from odoo.addons.veron_core.models import jalali

_lt = LazyTranslate(__name__)

MODULE = "veron_ai_agent_account"
EXPENSE_TYPES = ("expense", "expense_direct_cost", "expense_depreciation", "expense_other")
LIMIT = {"type": "integer", "minimum": 1, "maximum": 100}


def _r(value):
	return round(value or 0.0, 2)


def _today(ctx):
	return fields.Date.context_today(ctx.env.user)


class FinanceTool(Tool):
	module = MODULE
	category = "analyze"

	def plan(self, ctx, args):
		for model in self.models:
			ctx.check_model(model)
		return Plan(summary=self.label(ctx.env), model=self.models[0] if self.models else "")


# The rules of a draft invoice made by an assistant, set in the AI settings (a decision of the business)
PARAM_TAXES = "veron_ai_agent_account.invoice_taxes"  # ask | product | none
PARAM_PRICE = "veron_ai_agent_account.invoice_price"  # pricelist_history | pricelist
PARAM_DISCOUNT = "veron_ai_agent_account.invoice_discount"  # consistent | said
# A price at or under this is the empty default of a product (1), not a price
NO_PRICE = 1.0
# How many of the last sales of a product to a customer must agree for their discount to be used
HISTORY = 3


def invoice_policy(env):
	get = env["ir.config_parameter"].sudo().get_param
	return {"taxes": get(PARAM_TAXES, "ask"), "price": get(PARAM_PRICE, "pricelist_history"),
		"discount": get(PARAM_DISCOUNT, "consistent")}


@tool
class InvoiceDraftCreate(FinanceTool):
	code = "invoice_draft_create"
	name = _lt("Make a Draft Invoice")
	description = _lt("Makes a draft customer invoice or vendor bill from a contact and lines, all checked first: if a "
		"product has no price (said, in the customer's price list, in its last posted sale to the same customer when "
		"the settings allow, or on the product), or the taxes are not said nor set, nothing is made and the reason is "
		"given. A discount is the one said, or the same discount of the customer's last posted sales of the same "
		"product when they agree. It is never posted here.")
	category = "draft"
	action = "draft"
	risk = "medium"
	models = ("account.move", "res.partner", "product.product")
	schema = strict_object({
		"move_type": {"type": "string", "enum": ["out_invoice", "in_invoice"]},
		"partner_id": {"type": "integer", "minimum": 1},
		"invoice_date": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD"},
		"ref": {"type": "string", "maxLength": 100, "description": "The vendor's invoice number, for a bill"},
		"taxes": {"type": "string", "enum": ["product", "none"],
			"description": "product: the taxes set on each product; none: no taxes. Left out: the AI settings decide"},
		"lines": {"type": "array", "minItems": 1, "maxItems": 50, "items": strict_object({
			"product_id": {"type": "integer", "minimum": 1},
			"description": {"type": "string", "maxLength": 300},
			"quantity": {"type": "number", "minimum": 0},
			"price_unit": {"type": "number", "minimum": 0},
			"discount": {"type": "number", "minimum": 0, "maximum": 100, "description": "Percent"},
			"discount_from_history": {"type": "boolean",
				"description": "The customer's usual discount on this product, from its last posted sales"},
		}, ["quantity"])},
		"source_id": {"type": "integer", "minimum": 1, "description": "A file of this run to attach, e.g. the vendor's invoice"},
	}, ["move_type", "partner_id", "lines"])

	def _records(self, ctx, args):
		partners, domain = scoped(ctx, "res.partner", [("id", "=", args["partner_id"])])
		partner = partners.search(domain, limit=1)
		if not partner:
			raise ToolDenied(ctx.env._("No such contact in the agent's data."))
		ids = [line["product_id"] for line in args["lines"] if line.get("product_id")]
		products = ctx.env["product.product"]
		if ids:
			model, domain = scoped(ctx, "product.product", [("id", "in", ids)])
			products = model.search(domain)
			if set(products.ids) != set(ids):
				raise ToolDenied(ctx.env._("A product is not in the agent's data."))
		for line in args["lines"]:
			if not line.get("product_id") and not line.get("description"):
				raise ToolDenied(ctx.env._("A line without a product needs a description."))
			if not line.get("product_id") and line.get("price_unit") is None:
				raise ToolDenied(ctx.env._("A line without a product needs a price."))
		return partner, products

	def _sales(self, ctx, args, partner, product, limit=HISTORY):
		"""The last lines of posted invoices (not drafts, not cancelled, not credit notes) of this product to this
		customer, the newest first"""
		domain = [("move_id.move_type", "=", args["move_type"]), ("parent_state", "=", "posted"),
			("display_type", "=", "product"), ("product_id", "=", product.id),
			("move_id.partner_id.commercial_partner_id", "=", partner.commercial_partner_id.id)]
		try:
			return ctx.env["account.move.line"].search(domain, order="date desc, id desc", limit=limit)
		except AccessError:
			return ctx.env["account.move.line"]

	def _pricelist_price(self, partner, product, quantity):
		"""The price of the customer's price list when a rule of it applies to the product, else None"""
		pricelist = "property_product_pricelist" in partner._fields and partner.property_product_pricelist
		if not pricelist:
			return None, None
		try:
			price, rule = pricelist._get_product_price_rule(product, quantity or 1.0)
		except Exception:  # noqa: BLE001 - a price list that cannot price this product gives no price
			return None, None
		return (price, pricelist) if rule else (None, None)

	def _terms(self, ctx, args, line, partner, products, policy):
		"""Price, discount and taxes of a line, each with where it came from; nothing made up"""
		product = products.browse(line["product_id"]) if line.get("product_id") else products.browse()
		sales = self._sales(ctx, args, partner, product) if product else ctx.env["account.move.line"]
		terms = {"product": product, "price_unit": None, "price_from": "", "discount": 0.0, "discount_from": "",
			"note": "", "sales": sales}
		if line.get("price_unit") is not None:
			terms.update(price_unit=line["price_unit"], price_from=ctx.env._("said"))
		elif product:
			price, pricelist = self._pricelist_price(partner, product, line.get("quantity")) \
				if args["move_type"] == "out_invoice" else (None, None)
			if price is not None and price > NO_PRICE:
				terms.update(price_unit=price, price_from=pricelist.display_name)
			elif policy["price"] == "pricelist_history" and sales and sales[0].price_unit > NO_PRICE:
				terms.update(price_unit=sales[0].price_unit, price_from=sales[0].move_id.display_name)
			else:
				own = product.lst_price if args["move_type"] == "out_invoice" else product.standard_price
				if own > NO_PRICE:
					terms.update(price_unit=own, price_from=ctx.env._("price of the product"))
		if line.get("discount") is not None:
			terms.update(discount=line["discount"], discount_from=ctx.env._("said"))
		elif product and (line.get("discount_from_history") or policy["discount"] == "consistent"):
			discounts = sorted(set(sales.mapped("discount")))
			if len(discounts) == 1 and discounts[0]:
				terms.update(discount=discounts[0], discount_from=ctx.env._("the same in the last %(count)s sales (%(moves)s)",
					count=len(sales), moves=", ".join(sales.move_id.mapped("display_name"))))
			elif len(discounts) > 1:
				# Not the same each time: none is used, and the person is told
				terms["note"] = ctx.env._("%(product)s: the last discounts to this customer differ (%(values)s); none is "
					"used. Say the discount if one is wanted.", product=product.display_name,
					values=", ".join(f"{d:g}%" for d in discounts))
			elif line.get("discount_from_history"):
				terms["note"] = ctx.env._("%s: no earlier discount of this product to this customer; none is used.",
					product.display_name)
		return terms

	def _taxes(self, ctx, args, policy):
		taxes = args.get("taxes") or (policy["taxes"] if policy["taxes"] in ("product", "none") else None)
		if not taxes:
			raise ToolDenied(ctx.env._("Say whether taxes apply: «with taxes» (as set on the products) or «without taxes»."))
		return taxes

	def _checked(self, ctx, args):
		"""Everything checked before anything is made: a line without a price stops the whole invoice"""
		partner, products = self._records(ctx, args)
		policy = invoice_policy(ctx.env)
		taxes = self._taxes(ctx, args, policy)
		lines = [self._terms(ctx, args, line, partner, products, policy) for line in args["lines"]]
		unpriced = [terms["product"].display_name for terms in lines if terms["price_unit"] is None]
		if unpriced:
			raise ToolDenied(ctx.env._("No price for: %s. It is not in the customer's price list, not sold to them "
				"before and has no sale price on the product. Say the price («به قیمت ...») or set it on the product. No "
				"invoice was made.",
				", ".join(unpriced)))
		return partner, taxes, lines

	def plan(self, ctx, args):
		ctx.check_model("account.move")
		partner, _taxes, lines = self._checked(ctx, args)
		amount = sum(line["quantity"] * terms["price_unit"] * (1 - terms["discount"] / 100)
			for line, terms in zip(args["lines"], lines))
		kind = ctx.env._("customer invoice") if args["move_type"] == "out_invoice" else ctx.env._("vendor bill")
		return Plan(summary=ctx.env._("Draft %(kind)s for %(partner)s, %(amount)s before taxes", kind=kind,
			partner=partner.display_name, amount=f"{amount:,.0f}"), amount=amount, model="account.move",
			company_ids=[ctx.env.company.id])

	def execute(self, ctx, args, plan):
		partner, taxes, checked = self._checked(ctx, args)
		lines, notes, sources = [], [], []
		for line, terms in zip(args["lines"], checked):
			values = {"quantity": line["quantity"], "price_unit": terms["price_unit"], "discount": terms["discount"]}
			if line.get("product_id"):
				values["product_id"] = line["product_id"]
				product = terms["product"]
				own = product.taxes_id if args["move_type"] == "out_invoice" else product.supplier_taxes_id
				values["tax_ids"] = [(6, 0, own.filtered(lambda t: t.company_id == ctx.env.company).ids if taxes == "product" else [])]
			elif taxes == "none":
				values["tax_ids"] = [(6, 0, [])]
			if line.get("description"):
				values["name"] = line["description"]
			lines.append((0, 0, values))
			if terms["note"]:
				notes.append(terms["note"])
			sources.append({"product": terms["product"].display_name or line.get("description"),
				"price_from": terms["price_from"], "discount_from": terms["discount_from"] or "-"})
		values = {"move_type": args["move_type"], "partner_id": partner.id, "invoice_line_ids": lines,
			"ref": args.get("ref") or False}
		if args.get("invoice_date"):
			try:
				values["invoice_date"] = fields.Date.to_date(args["invoice_date"])
			except ValueError as error:
				raise ToolDenied(ctx.env._("Dates are written YYYY-MM-DD.")) from error
		move = ctx.env["account.move"].create(values)
		if args.get("source_id"):
			source = ctx.sources([args["source_id"]])
			if source and source.sudo().attachment_id:
				source.sudo().attachment_id.copy({"res_model": "account.move", "res_id": move.id})
		ctx.link(move)
		taxes_label = ctx.env._("as set on the products") if taxes == "product" else ctx.env._("none")
		return dict(_draft_output(move), sources=sources, taxes_rule=taxes_label, notes=notes)


def _draft_output(move):
	"""A draft invoice as the answer shows it: its lines and totals"""
	return {"draft_id": move.id, "draft": move.display_name, "partner": move.partner_id.display_name,
		"lines": [{"product": item.product_id.display_name or item.name, "quantity": item.quantity,
			"price": _r(item.price_unit), "discount": item.discount, "taxes": ", ".join(item.tax_ids.mapped("name")) or "-",
			"amount": _r(item.price_subtotal)} for item in move.invoice_line_ids],
		"untaxed": _r(move.amount_untaxed), "tax": _r(move.amount_tax), "total": _r(move.amount_total), "posted": False}


@tool
class InvoiceDraftUpdate(FinanceTool):
	code = "invoice_draft_update"
	name = _lt("Change a Draft Invoice")
	description = _lt("Changes a draft invoice or bill that is not posted: a discount (percent) on all its lines or "
		"on the line of a product, the count or the price of a line, the taxes taken off, lines added, a line taken "
		"out. A posted one is never changed here.")
	category = "draft"
	action = "draft"
	risk = "medium"
	models = ("account.move", "product.product")
	schema = strict_object({
		"move_id": {"type": "integer", "minimum": 1},
		"product_id": {"type": "integer", "minimum": 1, "description": "The line changed; none for all lines"},
		"discount": {"type": "number", "minimum": 0, "maximum": 100},
		"quantity": {"type": "number", "minimum": 0},
		"price_unit": {"type": "number", "minimum": 0},
		"add_lines": {"type": "array", "maxItems": 50, "items": strict_object({
			"product_id": {"type": "integer", "minimum": 1}, "quantity": {"type": "number", "minimum": 0},
		}, ["product_id"])},
		"remove_product_id": {"type": "integer", "minimum": 1},
		"remove_taxes": {"type": "boolean", "description": "Takes the taxes off all lines, or off the line of product_id"},
	}, ["move_id"])

	def _move(self, ctx, args):
		model, domain = scoped(ctx, "account.move", [("id", "=", args["move_id"])])
		move = model.search(domain, limit=1)
		if not move:
			raise ToolDenied(ctx.env._("No such invoice in the agent's data."))
		if move.state != "draft":
			raise ToolDenied(ctx.env._("%s is posted; a posted invoice is not changed here.", move.display_name))
		return move

	def _lines(self, ctx, move, product_id):
		lines = move.invoice_line_ids.filtered(lambda line: line.display_type == "product")
		if product_id:
			lines = lines.filtered(lambda line: line.product_id.id == product_id)
			if not lines:
				raise ToolDenied(ctx.env._("This draft has no line of that product."))
		return lines

	def plan(self, ctx, args):
		ctx.check_model("account.move")
		move = self._move(ctx, args)
		if not any(key in args for key in ("discount", "quantity", "price_unit", "add_lines", "remove_product_id",
				"remove_taxes")):
			raise ToolDenied(ctx.env._("Say what to change: a discount, a count, a price, a line to add or take out."))
		return Plan(summary=ctx.env._("Change the draft %s", move.display_name), amount=move.amount_untaxed,
			model="account.move", res_ids=[move.id], company_ids=[move.company_id.id])

	def execute(self, ctx, args, plan):
		move = self._move(ctx, args)
		lines = self._lines(ctx, move, args.get("product_id"))
		values = {key: args[key] for key in ("discount", "price_unit") if key in args}
		if "quantity" in args:
			if len(lines) > 1:
				raise ToolDenied(ctx.env._("Which product's count? The draft has several lines."))
			values["quantity"] = args["quantity"]
		if args.get("remove_taxes"):
			values["tax_ids"] = [(5, 0, 0)]
		if values:
			lines.write(values)
		if args.get("remove_product_id"):
			move.invoice_line_ids.filtered(lambda line: line.product_id.id == args["remove_product_id"]).unlink()
		if args.get("add_lines"):
			creator = InvoiceDraftCreate()
			product_ids = [line["product_id"] for line in args["add_lines"]]
			model, domain = scoped(ctx, "product.product", [("id", "in", product_ids)])
			products = model.search(domain)
			if set(products.ids) != set(product_ids):
				raise ToolDenied(ctx.env._("A product is not in the agent's data."))
			policy = invoice_policy(ctx.env)
			# The taxes of an added line follow the draft's own: its lines have taxes, or none have
			kept = self._lines(ctx, move, None)
			taxes = ("product" if kept.tax_ids else "none") if kept else creator._taxes(ctx, args, policy)
			made, unpriced = [], []
			for line in args["add_lines"]:
				line = dict(line, quantity=line.get("quantity", 1))
				terms = creator._terms(ctx, {"move_type": move.move_type}, line, move.partner_id, products, policy)
				if terms["price_unit"] is None:
					unpriced.append(terms["product"].display_name)
					continue
				product = terms["product"]
				own = product.taxes_id if move.move_type == "out_invoice" else product.supplier_taxes_id
				made.append((0, 0, {"product_id": line["product_id"], "quantity": line["quantity"],
					"price_unit": terms["price_unit"], "discount": terms["discount"],
					"tax_ids": [(6, 0, own.filtered(lambda t: t.company_id == move.company_id).ids if taxes == "product" else [])]}))
			if unpriced:
				raise ToolDenied(ctx.env._("No price for: %s. Say the price («به قیمت ...») or set it on the product.",
					", ".join(unpriced)))
			move.write({"invoice_line_ids": made})
		ctx.link(move)
		return _draft_output(move)


@tool
class SalesDocumentsRead(FinanceTool):
	code = "sales_documents_read"
	name = _lt("Read Quotations, Orders and Invoices")
	description = _lt("The lines and totals of quotations, sale orders, customer invoices or vendor bills, by their "
		"number or their contact, the newest first; drafts or posted ones as asked. Nothing is changed.")
	category = "read"
	models = ("res.partner",)
	KINDS = {"quotation": "sale.order", "order": "sale.order", "invoice": "account.move", "bill": "account.move"}
	schema = strict_object({
		"kind": {"type": "string", "enum": ["quotation", "order", "invoice", "bill"]},
		"ref": {"type": "string", "maxLength": 64, "description": "The number of the document, e.g. S00051"},
		"partner_id": {"type": "integer", "minimum": 1},
		"state": {"type": "string", "enum": ["draft", "done", "any"]},
		"limit": {"type": "integer", "minimum": 1, "maximum": 20},
	}, ["kind"])

	def available(self, env):
		return "account.move" in env

	def _domain(self, args):
		kind, state = args["kind"], args.get("state") or "any"
		if kind in ("quotation", "order"):
			domain = [("state", "in", ("draft", "sent"))] if kind == "quotation" else [("state", "=", "sale")]
			if kind == "quotation" and state == "done":
				domain = [("state", "=", "sale")]
		else:
			domain = [("move_type", "=", "out_invoice" if kind == "invoice" else "in_invoice")]
			if state == "draft":
				domain.append(("state", "=", "draft"))
			elif state == "done":
				domain.append(("state", "=", "posted"))
			else:
				domain.append(("state", "!=", "cancel"))
		return domain

	def plan(self, ctx, args):
		model = self.KINDS[args["kind"]]
		if model not in ctx.env:
			raise ToolDenied(ctx.env._("%s is not installed.", model))
		ctx.check_model(model)
		return Plan(summary=self.label(ctx.env), model=model)

	def execute(self, ctx, args, plan):
		model_name = self.KINDS[args["kind"]]
		extra = self._domain(args)
		if args.get("partner_id"):
			partner = ctx.env["res.partner"].browse(args["partner_id"]).exists()
			if not partner:
				raise ToolDenied(ctx.env._("No such contact in the agent's data."))
			extra.append(("partner_id", "child_of", partner.commercial_partner_id.id))
		model, domain = scoped(ctx, model_name, extra)
		if args.get("ref"):
			ref = args["ref"].strip()
			found = model.search(domain & Domain("name", "=ilike", ref), limit=1) or \
				model.search(domain & Domain("name", "ilike", ref), limit=2)
			if len(found) != 1:
				raise ToolDenied(ctx.env._("No document numbered %s among those you may see.", ref) if not found else
					ctx.env._("More than one document is numbered like %s; write the whole number.", ref))
			documents = found
		else:
			documents = model.search(domain, limit=args.get("limit") or 5, order="id desc")
		ctx.link(documents)
		result = []
		for document in documents:
			if model_name == "sale.order":
				items = document.order_line.filtered(lambda line: not line.display_type)
				lines = [{"product": line.product_id.display_name or line.name, "quantity": line.product_uom_qty,
					"price": _r(line.price_unit), "discount": line.discount,
					"taxes": ", ".join(line.tax_ids.mapped("name")) or "-", "amount": _r(line.price_subtotal)} for line in items]
				date = document.date_order
			else:
				items = document.invoice_line_ids.filtered(lambda line: line.display_type == "product")
				lines = [{"product": line.product_id.display_name or line.name, "quantity": line.quantity,
					"price": _r(line.price_unit), "discount": line.discount,
					"taxes": ", ".join(line.tax_ids.mapped("name")) or "-", "amount": _r(line.price_subtotal)} for line in items]
				date = document.invoice_date or document.date
			result.append({"document": document.display_name, "partner": document.partner_id.display_name,
				"date": str(date or ""), "state": dict(document._fields["state"]._description_selection(ctx.env)).get(document.state),
				"lines": lines, "untaxed": _r(document.amount_untaxed), "tax": _r(document.amount_tax),
				"total": _r(document.amount_total)})
		return {"count": len(result), "documents": result}


@tool
class ReceivablesOverdue(FinanceTool):
	code = "receivables_overdue"
	name = _lt("Overdue Receivables")
	description = _lt("Posted customer invoices past their due date and not fully paid, by customer, the largest first.")
	category = "read"
	models = ("account.move",)
	schema = strict_object({"min_days": {"type": "integer", "minimum": 0, "maximum": 3650}, "limit": LIMIT})

	def execute(self, ctx, args, plan):
		today = _today(ctx)
		due = today - timedelta(days=args.get("min_days") or 0)
		model, domain = scoped(ctx, "account.move", [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
			("payment_state", "in", ("not_paid", "partial")), ("invoice_date_due", "<", due)])
		invoices = model.search(domain, order="invoice_date_due")
		by_partner = {}
		for invoice in invoices:
			key = invoice.partner_id.commercial_partner_id
			item = by_partner.setdefault(key, {"customer": key.display_name, "invoices": 0, "amount_due": 0.0, "oldest_days": 0})
			item["invoices"] += 1
			item["amount_due"] += invoice.amount_residual_signed
			item["oldest_days"] = max(item["oldest_days"], (today - invoice.invoice_date_due).days)
		rows = sorted(by_partner.values(), key=lambda r: -r["amount_due"])[:args.get("limit") or 20]
		for row in rows:
			row["amount_due"] = _r(row["amount_due"])
		ctx.link(invoices[:20])
		return {"date": str(today), "customers": rows, "invoices": len(invoices),
			"total_due": _r(sum(invoices.mapped("amount_residual_signed"))), "currency": ctx.env.company.currency_id.name}


@tool
class PayablesDue(FinanceTool):
	code = "payables_due"
	name = _lt("Payables Due")
	description = _lt("Posted vendor bills not fully paid that are overdue or due in the next N days.")
	category = "read"
	models = ("account.move",)
	schema = strict_object({"days": {"type": "integer", "minimum": 0, "maximum": 365}, "limit": LIMIT})

	def execute(self, ctx, args, plan):
		today = _today(ctx)
		until = today + timedelta(days=args.get("days", 7))
		model, domain = scoped(ctx, "account.move", [("move_type", "=", "in_invoice"), ("state", "=", "posted"),
			("payment_state", "in", ("not_paid", "partial")), ("invoice_date_due", "<=", until)])
		bills = model.search(domain, order="invoice_date_due", limit=args.get("limit") or 30)
		ctx.link(bills)
		return {"until": str(until), "bills": [{"id": b.id, "bill": b.name, "vendor": b.partner_id.display_name,
			"due": str(b.invoice_date_due), "overdue": b.invoice_date_due < today, "amount_due": _r(-b.amount_residual_signed)}
			for b in bills], "total_due": _r(-sum(bills.mapped("amount_residual_signed")))}


@tool
class ExpenseSummary(FinanceTool):
	code = "expense_summary"
	name = _lt("Expenses of a Period")
	description = _lt("Posted expenses of a period by account, from the journal items, with the total.")
	models = ("account.move.line",)
	schema = strict_object({**PERIOD, "limit": LIMIT})

	def execute(self, ctx, args, plan):
		start, end = period(ctx, args, 30)
		model, domain = scoped(ctx, "account.move.line", [("parent_state", "=", "posted"), ("date", ">=", start),
			("date", "<=", end), ("account_id.account_type", "in", EXPENSE_TYPES)])
		rows = model._read_group(domain, ["account_id"], ["balance:sum"], order="balance:sum desc",
			limit=args.get("limit") or 30)
		total = model._read_group(domain, [], ["balance:sum"])[0][0]
		return {"period": f"{start} - {end}", "total": _r(total), "currency": ctx.env.company.currency_id.name,
			"by_account": [{"account": account.display_name, "amount": _r(amount)} for account, amount in rows]}


@tool
class CashPosition(FinanceTool):
	code = "cash_position"
	name = _lt("Cash and Bank Balances")
	description = _lt("The posted balance of each bank and cash journal, and of each petty cash fund the agent may see.")
	category = "read"
	models = ("account.journal", "account.move.line")
	schema = strict_object({})

	def execute(self, ctx, args, plan):
		journals, domain = scoped(ctx, "account.journal", [("type", "in", ("bank", "cash")), ("default_account_id", "!=", False)])
		lines, line_domain = scoped(ctx, "account.move.line", [("parent_state", "=", "posted")])
		result = []
		for journal in journals.search(domain):
			balance = lines._read_group(line_domain & Domain("account_id", "=", journal.default_account_id.id), [],
				["balance:sum"])[0][0]
			result.append({"journal": journal.name, "type": journal.type, "account": journal.default_account_id.code,
				"balance": _r(balance)})
		funds = []
		if ctx.agent._scope("veron.petty.cash.fund"):
			model, fund_domain = scoped(ctx, "veron.petty.cash.fund")
			funds = [{"fund": f.name, "custodian": f.custodian_user_id.name, "balance": _r(f.balance)}
				for f in model.search(fund_domain)]
		return {"date": str(_today(ctx)), "journals": result, "petty_cash": funds,
			"total": _r(sum(r["balance"] for r in result) + sum(f["balance"] for f in funds)),
			"currency": ctx.env.company.currency_id.name}


@tool
class BankUnreconciled(FinanceTool):
	code = "bank_unreconciled"
	name = _lt("Unreconciled Bank Lines")
	description = _lt("Bank statement lines not reconciled, each with the open invoices or bills of the same amount as "
		"suggestions. It only suggests; an accountant reconciles.")
	category = "read"
	models = ("account.bank.statement.line", "account.move")
	schema = strict_object({"limit": LIMIT})

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, "account.bank.statement.line", [("is_reconciled", "=", False)])
		lines = model.search(domain, order="date desc", limit=args.get("limit") or 30)
		moves, move_domain = scoped(ctx, "account.move", [("state", "=", "posted"),
			("payment_state", "in", ("not_paid", "partial")), ("move_type", "in", ("out_invoice", "in_invoice"))])
		result = []
		for line in lines:
			kind = "out_invoice" if line.amount > 0 else "in_invoice"
			candidates = moves.search(move_domain & Domain([("move_type", "=", kind),
				("amount_residual", "=", abs(line.amount))]), limit=5)
			if line.partner_id:
				candidates = candidates.sorted(lambda m: m.commercial_partner_id != line.partner_id.commercial_partner_id)
			result.append({"id": line.id, "date": str(line.date), "label": line.payment_ref, "amount": _r(line.amount),
				"partner": line.partner_id.display_name or None, "journal": line.journal_id.name,
				"suggestions": [{"document": m.name, "partner": m.partner_id.display_name, "due": _r(m.amount_residual)}
					for m in candidates]})
		ctx.link(lines[:20])
		return {"lines": result, "note": "Suggestions only; the same amount is not proof of the same payment."}


@tool
class DocumentsQuality(FinanceTool):
	code = "documents_quality"
	name = _lt("Quality of Accounting Documents")
	description = _lt("Accounting documents of a period that need attention: old drafts, bills without the vendor's "
		"number or without an attached file, and vendor numbers used twice.")
	models = ("account.move",)
	schema = strict_object({**PERIOD, "draft_days": {"type": "integer", "minimum": 1, "maximum": 365}})

	def execute(self, ctx, args, plan):
		start, end = period(ctx, args, 31)
		model, domain = scoped(ctx, "account.move", [("date", ">=", start), ("date", "<=", end)])
		old = _today(ctx) - timedelta(days=args.get("draft_days") or 7)
		drafts = model.search(domain & Domain([("state", "=", "draft"), ("create_date", "<", old)]), limit=50)
		bills = model.search(domain & Domain([("state", "=", "posted"), ("move_type", "in", ("in_invoice", "in_refund"))]))
		no_ref = bills.filtered(lambda m: not m.ref)
		attached = set(ctx.env["ir.attachment"].search([("res_model", "=", "account.move"), ("res_id", "in", bills.ids)]).mapped("res_id"))
		no_file = bills.filtered(lambda m: m.id not in attached)
		seen, twice = {}, []
		for bill in bills.filtered("ref"):
			key = (bill.commercial_partner_id.id, bill.ref.strip().lower())
			if key in seen:
				twice.append({"bill": bill.name, "same_as": seen[key], "vendor": bill.partner_id.display_name, "number": bill.ref})
			else:
				seen[key] = bill.name
		ctx.link((drafts | no_ref | no_file)[:20])

		def names(records):
			return [{"id": m.id, "document": m.display_name, "date": str(m.date)} for m in records[:30]]

		return {"period": f"{start} - {end}", "old_drafts": names(drafts), "bills_without_vendor_number": names(no_ref),
			"bills_without_file": names(no_file), "vendor_number_twice": twice[:30],
			"note": "These are to check; a missing file may be kept on paper."}


@tool
class MonthEndChecklist(FinanceTool):
	code = "month_end_checklist"
	name = _lt("Month-End Checklist")
	description = _lt("Before closing a Shamsi month: drafts dated in it, unreconciled bank lines, open petty cash "
		"closings, depreciation not posted and the lock dates. It closes nothing.")
	models = ("account.move",)
	schema = strict_object({"month": {"type": "string", "maxLength": 7, "description": "Shamsi year/month, e.g. 1405/07; "
		"the last month by default"}})

	def execute(self, ctx, args, plan):
		today = _today(ctx)
		if args.get("month"):
			try:
				year, month = (int(p) for p in args["month"].replace("-", "/").split("/"))
				start = jalali.to_gregorian(year, month, 1)
			except (ValueError, TypeError) as error:
				raise ToolDenied(ctx.env._("The month is written as 1405/07.")) from error
		else:
			year, month, _day = jalali.to_jalali(today)
			year, month = (year, month - 1) if month > 1 else (year - 1, 12)
			start = jalali.to_gregorian(year, month, 1)
		end = jalali.to_gregorian(year, month, jalali.month_length(year, month))
		items = []
		moves, domain = scoped(ctx, "account.move", [("date", ">=", start), ("date", "<=", end), ("state", "=", "draft")])
		drafts = moves.search_count(domain)
		items.append({"check": "Draft documents dated in the month", "count": drafts, "ok": not drafts})
		if "account.bank.statement.line" in ctx.env and ctx.agent._scope("account.bank.statement.line"):
			model, line_domain = scoped(ctx, "account.bank.statement.line", [("is_reconciled", "=", False), ("date", "<=", end)])
			count = model.search_count(line_domain)
			items.append({"check": "Unreconciled bank lines up to the month's end", "count": count, "ok": not count})
		if ctx.agent._scope("veron.petty.cash.closing"):
			model, closing_domain = scoped(ctx, "veron.petty.cash.closing", [("state", "in", ("draft", "review", "to_approve")),
				("date_from", "<=", end)])
			count = model.search_count(closing_domain)
			items.append({"check": "Petty cash closings not posted", "count": count, "ok": not count})
		if "account.asset.line" in ctx.env and ctx.agent._scope("account.asset.line"):
			model, asset_domain = scoped(ctx, "account.asset.line", [("type", "=", "depreciate"), ("line_date", "<=", end),
				("move_check", "=", False)])
			count = model.search_count(asset_domain)
			items.append({"check": "Depreciation lines not posted", "count": count, "ok": not count})
		company = ctx.env.company
		locks = {name: str(company[name]) if company[name] else None for name in
			("fiscalyear_lock_date", "tax_lock_date", "sale_lock_date", "purchase_lock_date") if name in company._fields}
		items.append({"check": "Lock dates", "values": locks,
			"ok": bool(locks.get("fiscalyear_lock_date") and company.fiscalyear_lock_date >= end)})
		return {"month": f"{year}/{month:02d}", "from": str(start), "to": str(end), "items": items,
			"note": "Locking the period is done by a person in accounting."}


@tool
class TaxSummary(FinanceTool):
	code = "tax_summary"
	name = _lt("VAT of a Period")
	description = _lt("Posted tax amounts and their bases of a period, by tax, to check before the VAT return. It "
		"prepares nothing legal; the return is made and sent by a person.")
	models = ("account.move.line",)
	schema = strict_object(PERIOD)

	def execute(self, ctx, args, plan):
		start, end = period(ctx, args, 90)
		model, domain = scoped(ctx, "account.move.line", [("parent_state", "=", "posted"), ("date", ">=", start),
			("date", "<=", end)])
		taxes = model._read_group(domain & Domain("tax_line_id", "!=", False), ["tax_line_id"], ["balance:sum"])
		bases = model._read_group(domain & Domain("tax_ids", "!=", False), ["tax_ids"], ["balance:sum"])
		base_of = {tax.id: amount for tax, amount in bases}
		rows = [{"tax": tax.display_name, "type": tax.type_tax_use, "tax_amount": _r(-amount if tax.type_tax_use == "sale" else amount),
			"base": _r(-base_of.get(tax.id, 0.0) if tax.type_tax_use == "sale" else base_of.get(tax.id, 0.0))}
			for tax, amount in taxes]
		return {"period": f"{start} - {end}", "taxes": rows, "currency": ctx.env.company.currency_id.name,
			"note": "For checking only. Rates and rules come from the taxes set in Odoo, not from the agent."}


@tool
class BudgetVsActual(FinanceTool):
	code = "budget_vs_actual"
	name = _lt("Budget Against Actual")
	description = _lt("Budget lines of the current period (or the one given) with planned, actual and the difference, the furthest first.")
	models = ("crossovered.budget.lines",)
	schema = strict_object({"date": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD within the budget; today by default"},
		"limit": LIMIT})

	def execute(self, ctx, args, plan):
		try:
			day = fields.Date.to_date(args["date"]) if args.get("date") else _today(ctx)
		except ValueError as error:
			raise ToolDenied(ctx.env._("Dates are written YYYY-MM-DD.")) from error
		model, domain = scoped(ctx, "crossovered.budget.lines", [("date_from", "<=", day), ("date_to", ">=", day)])
		lines = model.search(domain)
		rows = [{"budget": line.crossovered_budget_id.display_name, "position": line.general_budget_id.display_name,
			"analytic": line.analytic_account_id.display_name or None, "planned": _r(line.planned_amount),
			"actual": _r(line.practical_amount), "difference": _r(line.practical_amount - line.planned_amount),
			"percent_of_expected": _r(line.percentage * 100)} for line in lines]
		rows.sort(key=lambda r: -abs(r["difference"]))
		return {"date": str(day), "lines": rows[:args.get("limit") or 30]}


@tool
class AssetCheck(FinanceTool):
	code = "asset_check"
	name = _lt("Fixed Assets to Check")
	description = _lt("Draft assets, and running assets with depreciation due but not posted.")
	models = ("account.asset", "account.asset.line")
	schema = strict_object({"limit": LIMIT})

	def execute(self, ctx, args, plan):
		today = _today(ctx)
		assets, domain = scoped(ctx, "account.asset", [("state", "=", "draft")])
		drafts = assets.search(domain, limit=args.get("limit") or 30)
		lines, line_domain = scoped(ctx, "account.asset.line", [("type", "=", "depreciate"), ("line_date", "<=", today),
			("move_check", "=", False), ("asset_id.state", "=", "open")])
		due = lines.search(line_domain, limit=200)
		by_asset = {}
		for line in due:
			item = by_asset.setdefault(line.asset_id, {"asset": line.asset_id.display_name, "lines": 0, "amount": 0.0, "oldest": str(line.line_date)})
			item["lines"] += 1
			item["amount"] = _r(item["amount"] + line.amount)
		ctx.link(drafts[:20] | due.asset_id[:20])
		return {"date": str(today), "draft_assets": [{"asset": a.display_name, "value": _r(a.purchase_value)} for a in drafts],
			"depreciation_not_posted": list(by_asset.values())[:args.get("limit") or 30]}
