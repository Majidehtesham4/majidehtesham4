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


@tool
class InvoiceDraftCreate(FinanceTool):
	code = "invoice_draft_create"
	name = _lt("Make a Draft Invoice")
	description = _lt("Makes a draft customer invoice or vendor bill from a contact and lines. A price, discount or "
		"taxes left out are those of the last invoice of the same contact and product (else the product's price and "
		"the discount and taxes of the contact's last invoice); totals are computed by Odoo. It is never posted here.")
	category = "draft"
	action = "draft"
	risk = "medium"
	models = ("account.move", "res.partner", "product.product")
	schema = strict_object({
		"move_type": {"type": "string", "enum": ["out_invoice", "in_invoice"]},
		"partner_id": {"type": "integer", "minimum": 1},
		"invoice_date": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD"},
		"ref": {"type": "string", "maxLength": 100, "description": "The vendor's invoice number, for a bill"},
		"lines": {"type": "array", "minItems": 1, "maxItems": 50, "items": strict_object({
			"product_id": {"type": "integer", "minimum": 1},
			"description": {"type": "string", "maxLength": 300},
			"quantity": {"type": "number", "minimum": 0},
			"price_unit": {"type": "number", "minimum": 0},
			"discount": {"type": "number", "minimum": 0, "maximum": 100, "description": "Percent"},
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

	def _last(self, ctx, args, partner, product=None):
		"""The last line of a posted invoice of this contact (and product): what was agreed with them; without a
		contact, the last of the product to anyone"""
		domain = [("move_id.move_type", "=", args["move_type"]), ("parent_state", "=", "posted"),
			("display_type", "=", "product")]
		if partner:
			domain.append(("move_id.partner_id.commercial_partner_id", "=", partner.commercial_partner_id.id))
		if product:
			domain.append(("product_id", "=", product.id))
		try:
			return ctx.env["account.move.line"].search(domain, order="date desc, id desc", limit=1)
		except AccessError:
			return ctx.env["account.move.line"]

	def _terms(self, ctx, args, line, partner, products):
		"""Price, discount and taxes of a line: as given, else as on the last invoice of the contact"""
		product = products.browse(line["product_id"]) if line.get("product_id") else products.browse()
		same = self._last(ctx, args, partner, product) if product else ctx.env["account.move.line"]
		before = same or self._last(ctx, args, partner)
		anyone = self._last(ctx, args, None, product) if product and not same and line.get("price_unit") is None \
			else ctx.env["account.move.line"]
		if line.get("price_unit") is not None:
			price = line["price_unit"]
		elif same:
			price = same.price_unit
		elif anyone:
			# Not sold to this contact before: the price it was last sold at
			price = anyone.price_unit
		else:
			price = product.lst_price if args["move_type"] == "out_invoice" else product.standard_price
		discount = line["discount"] if line.get("discount") is not None else (before.discount if before else 0.0)
		return {"price_unit": price, "discount": discount, "taxes": before.tax_ids if before else None,
			"from": before | anyone, "no_price": bool(product) and price <= 1 and line.get("price_unit") is None}

	def plan(self, ctx, args):
		ctx.check_model("account.move")
		partner, products = self._records(ctx, args)
		amount = 0.0
		for line in args["lines"]:
			terms = self._terms(ctx, args, line, partner, products)
			amount += line["quantity"] * terms["price_unit"] * (1 - terms["discount"] / 100)
		kind = ctx.env._("customer invoice") if args["move_type"] == "out_invoice" else ctx.env._("vendor bill")
		return Plan(summary=ctx.env._("Draft %(kind)s for %(partner)s, %(amount)s before taxes", kind=kind,
			partner=partner.display_name, amount=f"{amount:,.0f}"), amount=amount, model="account.move",
			company_ids=[ctx.env.company.id])

	def execute(self, ctx, args, plan):
		partner, products = self._records(ctx, args)
		lines, sources, unpriced = [], ctx.env["account.move"], []
		for line in args["lines"]:
			terms = self._terms(ctx, args, line, partner, products)
			values = {"quantity": line["quantity"], "price_unit": terms["price_unit"], "discount": terms["discount"]}
			if line.get("product_id"):
				values["product_id"] = line["product_id"]
			if line.get("description"):
				values["name"] = line["description"]
			if terms["taxes"] is not None:
				# The taxes this contact was invoiced with, none when it had none
				values["tax_ids"] = [(6, 0, terms["taxes"].ids)]
			sources |= terms["from"].move_id
			if terms["no_price"]:
				unpriced.append(products.browse(line["product_id"]).display_name)
			lines.append((0, 0, values))
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
		return dict(_draft_output(move), terms_from=", ".join(sources.mapped("display_name")), no_price=unpriced)


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
			# A line added to a draft whose lines have one discount gets it too
			shared = set(self._lines(ctx, move, None).mapped("discount"))
			common = shared.pop() if len(shared) == 1 else 0.0
			made = []
			for line in args["add_lines"]:
				line = dict(line, quantity=line.get("quantity", 1))
				terms = creator._terms(ctx, {"move_type": move.move_type}, line, move.partner_id, products)
				discount = common or terms["discount"]
				item = {"product_id": line["product_id"], "quantity": line["quantity"], "price_unit": terms["price_unit"],
					"discount": discount}
				if terms["taxes"] is not None:
					item["tax_ids"] = [(6, 0, terms["taxes"].ids)]
				made.append((0, 0, item))
			move.write({"invoice_line_ids": made})
		ctx.link(move)
		return _draft_output(move)


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
