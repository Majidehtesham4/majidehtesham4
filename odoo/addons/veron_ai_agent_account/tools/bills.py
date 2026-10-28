"""A vendor bill from its file: the photo or the PDF is read (by the reading provider when one is set, or
from the text of the PDF without any AI), the vendor is found by its economic code or its name, and a
draft bill is made with the file attached. Posting is another tool, a sensitive one, that waits for a
person's approval."""

import re

from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.veron_ai_agent.services import nlu, reader
from odoo.addons.veron_ai_agent.services.registry import Plan, Tool, ToolDenied, tool
from odoo.addons.veron_ai_agent.services.schema import strict_object
from odoo.addons.veron_ai_agent.tools.common import scoped
from odoo.addons.veron_ai_agent.tools.documents import DOCUMENTS, INSTRUCTIONS

from ..models.petty_cash import _date, _number

_lt = LazyTranslate(__name__)
MODULE = "veron_ai_agent_account"


def text_fields(text):
	"""The fields of an Iranian invoice read from its text without any AI"""
	return reader.invoice(text)


def _plain_name(name):
	"""A name without the words every company has, to compare two ways of writing it"""
	name = nlu.normalize(name or "")
	name = re.sub(r"\b(شرکت|فروشگاه|سهامی|خاص|عام|مسئولیت|محدود|تعاونی|موسسه|گروه|بازرگانی|تولیدی|صنایع|co|ltd|inc)\b", " ", name)
	return re.sub(r"\s+", " ", name).strip()


def _same(name, others):
	"""Whether two names are of the same company: written the same, or alike once the common words are left out"""
	whole = nlu.normalize(name or "")
	if whole and any(whole == nlu.normalize(other or "") for other in others):
		return True
	name = _plain_name(name)
	return len(name) >= 3 and any(len(other) >= 3 and (name in other or other in name) for other in map(_plain_name, others))


@tool
class BillFromDocument(Tool):
	code = "bill_from_document"
	name = _lt("Make a Draft Invoice From Its File")
	description = _lt("Reads an invoice (a photo or a PDF given to this run) and makes a draft with the file attached: a "
		"customer invoice when the company is the seller on it, else a vendor bill. The other party is found by its "
		"economic code or its name, the rows of goods are read when quantity times price is the row total, and the "
		"total is checked against the amount written in words. Without any AI, the text of the PDF or the built-in "
		"OCR is read. It is never posted here.")
	category = "draft"
	action = "draft"
	risk = "medium"
	module = MODULE
	models = ("account.move", "res.partner")
	schema = strict_object({
		"source_id": {"type": "integer", "minimum": 1, "description": "A photo or a PDF of this run"},
		"direction": {"type": "string", "enum": ["auto", "sale", "purchase"],
			"description": "sale: the company sold (customer invoice); purchase: it bought (vendor bill); auto: from the file"},
	}, ["source_id"])

	def _read(self, ctx, source):
		result = source._extract(DOCUMENTS["invoice"], INSTRUCTIONS, ctx.provider("vision"), document_type="invoice")
		if not result or not (result.get("fields") or {}).get("total_amount") and not (result.get("fields") or {}).get("vendor"):
			raise ToolDenied(ctx.env._("Nothing could be read from the file. Send a clearer photo or the PDF of the invoice."))
		values = dict(result["fields"])
		values.setdefault("confidence", "medium")
		if result.get("reader") == "builtin":
			return values, ctx.env._("the built-in reader (no AI)")
		provider = ctx.provider("vision")
		return values, provider.name if provider else ctx.env._("the built-in reader (no AI)")

	def _direction(self, ctx, args, values):
		"""sale when the company is the seller on the invoice, purchase when it is the buyer"""
		if args.get("direction") in ("sale", "purchase"):
			return args["direction"]
		company = ctx.env.company
		ours = re.sub(r"\D", "", company.vat or company.partner_id.vat or "")
		names = [company.name, company.partner_id.name]
		seller_code = re.sub(r"\D", "", str(values.get("vendor_tax_id") or ""))
		buyer_code = re.sub(r"\D", "", str(values.get("buyer_tax_id") or ""))
		if ours and seller_code == ours or _same(values.get("vendor"), names):
			return "sale"
		if ours and buyer_code == ours or _same(values.get("buyer"), names):
			return "purchase"
		asked = nlu.normalize(ctx.run.input_text or "")
		if re.search(r"فاکتور فروش|فروختیم|فروخته", asked) and "خرید" not in asked:
			return "sale"
		return "purchase"

	def plan(self, ctx, args):
		ctx.check_model("account.move")
		source = ctx.sources([args["source_id"]])
		if not source or source.kind not in ("image", "pdf"):
			raise ToolDenied(ctx.env._("The file is not a photo or a PDF of this run."))
		values, reader = self._read(ctx, source)
		direction = self._direction(ctx, args, values)
		total = _number(values.get("total_amount")) or 0.0
		summary = ctx.env._("Draft customer invoice from %(file)s, %(amount)s", file=source.name, amount=f"{total:,.0f}") \
			if direction == "sale" else ctx.env._("Draft vendor bill from %(file)s, %(amount)s", file=source.name,
			amount=f"{total:,.0f}")
		return Plan(summary=summary, amount=total, model="account.move", company_ids=[ctx.env.company.id],
			data={"values": values, "reader": reader, "direction": direction})

	def _partner(self, ctx, name, code, rank):
		partners, domain = scoped(ctx, "res.partner")
		tax_id = re.sub(r"\D", "", str(code or ""))
		if tax_id:
			found = partners.search(domain & Domain("vat", "ilike", tax_id), limit=1)
			if found:
				return found
		name = str(name or "").strip()
		if len(name) >= 3:
			found = partners.search(domain & Domain("name", "ilike", name), limit=10)
			if not found and _plain_name(name):
				found = partners.search(domain & Domain("name", "ilike", _plain_name(name)), limit=10)
			exact = found.filtered(lambda p: (p.name or "").strip().lower() == name.lower())
			for candidates in (found, exact, exact.filtered(lambda p: p[rank])):
				if len(candidates) == 1:
					return candidates
		return partners.browse()

	def _account(self, ctx, partner, sale):
		"""The account of the rows: the journal's, else the partner's usual one, else the first income or expense"""
		move_type = "out_invoice" if sale else "in_invoice"
		journal = ctx.env["account.move"].with_context(default_move_type=move_type)._search_default_journal()
		account = journal.default_account_id
		if not account and partner:
			last = ctx.env["account.move.line"].search([("partner_id", "=", partner.id), ("move_id.move_type", "=", move_type),
				("display_type", "=", "product"), ("parent_state", "=", "posted")], order="id desc", limit=1)
			account = last.account_id
		if not account:
			account = ctx.env["account.account"].search([("account_type", "=", "income" if sale else "expense"),
				("active", "=", True), *ctx.env["account.account"]._check_company_domain(ctx.env.company)], limit=1)
		if not account:
			raise ToolDenied(ctx.env._("No income account was found; set the default account of the sales journal.") if sale
				else ctx.env._("No expense account was found; set the default account of the purchase journal."))
		return account

	def _tax(self, ctx, untaxed, vat, sale):
		if not untaxed or not vat:
			return ctx.env["account.tax"]
		rate = round(vat / untaxed * 100, 1)
		taxes = ctx.env["account.tax"].search([("type_tax_use", "=", "sale" if sale else "purchase"),
			("amount_type", "=", "percent"), ("company_id", "=", ctx.env.company.id)])
		return taxes.filtered(lambda t: abs(t.amount - rate) < 0.6)[:1]

	def execute(self, ctx, args, plan):
		source = ctx.sources([args["source_id"]])
		values = plan.data["values"]
		sale = plan.data.get("direction") == "sale"
		move_type = "out_invoice" if sale else "in_invoice"
		if sale:
			partner = self._partner(ctx, values.get("buyer"), values.get("buyer_tax_id"), "customer_rank")
			party = values.get("buyer")
		else:
			partner = self._partner(ctx, values.get("vendor"), values.get("vendor_tax_id"), "supplier_rank")
			party = values.get("vendor")
		number = str(values.get("invoice_number") or "").strip()[:60]
		if partner and number:
			moves, domain = scoped(ctx, "account.move", [("move_type", "=", move_type), ("ref", "=", number),
				("commercial_partner_id", "=", partner.commercial_partner_id.id), ("state", "!=", "cancel")])
			twin = moves.search(domain, limit=1)
			if twin:
				raise ToolDenied(ctx.env._("This invoice is already recorded as %s.", twin.display_name))
		total = _number(values.get("total_amount")) or 0.0
		vat = _number(values.get("vat_amount")) or 0.0
		untaxed = _number(values.get("untaxed_amount")) or (total - vat if total else 0.0)
		tax = self._tax(ctx, untaxed, vat, sale)
		label = ctx.env._("Invoice %(number)s of %(vendor)s", number=number or "-", vendor=partner.name or party or "-")
		lines = []
		for line in values.get("lines") or []:
			price = _number(line.get("unit_price"))
			quantity = _number(line.get("quantity")) or 1.0
			if line.get("description") and price:
				lines.append((0, 0, {"name": str(line["description"])[:250], "quantity": quantity, "price_unit": price,
					"tax_ids": [(6, 0, tax.ids)]}))
		if not lines or (untaxed and abs(sum(l[2]["quantity"] * l[2]["price_unit"] for l in lines) - untaxed) > 1):
			lines = [(0, 0, {"name": label, "quantity": 1, "price_unit": untaxed if tax else total, "tax_ids": [(6, 0, tax.ids)]})]
		account = self._account(ctx, partner, sale)
		for line in lines:
			line[2]["account_id"] = account.id
		move_values = {"move_type": move_type, "partner_id": partner.id or False, "ref": number or False,
			"invoice_line_ids": lines}
		date = _date(values.get("date"))
		if date:
			move_values["invoice_date"] = date
		move = ctx.env["account.move"].create(move_values)
		attachment = source.sudo().attachment_id
		if attachment:
			attachment.copy({"res_model": "account.move", "res_id": move.id})
		ctx.link(move)
		checks = []
		if not partner:
			checks.append(ctx.env._("The customer «%s» was not found; choose it on the invoice.", party or "-") if sale else
				ctx.env._("The vendor «%s» was not found; choose it on the bill.", party or "-"))
		if vat and not tax:
			checks.append(ctx.env._("No tax of this rate was found; the VAT is inside the amount."))
		if total and abs(move.amount_total - total) > 1:
			checks.append(ctx.env._("The total of the draft (%(draft)s) is not the total on the file (%(file)s); check the rows.",
				draft=f"{move.amount_total:,.0f}", file=f"{total:,.0f}"))
		if values.get("confidence") == "low":
			checks.append(ctx.env._("Read with low confidence; compare the bill with the file."))
		return {"draft_id": move.id, "draft": move.display_name,
			"kind": ctx.env._("Customer invoice") if sale else ctx.env._("Vendor bill"),
			"customer" if sale else "vendor": partner.display_name or party or None,
			"number": number or None, "date": str(date) if date else None, "lines": [
				{"description": l[2]["name"], "quantity": l[2]["quantity"], "price": l[2]["price_unit"]} for l in lines],
			"untaxed": round(move.amount_untaxed, 2), "tax": round(move.amount_tax, 2), "total": round(move.amount_total, 2),
			"read_by": plan.data.get("reader"), "to_check": checks, "posted": False}


@tool
class InvoicePost(Tool):
	code = "invoice_post"
	name = _lt("Post an Invoice or Bill")
	description = _lt("Posts a draft customer invoice or vendor bill. Posting always waits for a person's approval and is "
		"done with the rights of the person who approves it.")
	category = "execute"
	action = "execute"
	risk = "high"
	sensitive = "post"
	module = MODULE
	models = ("account.move",)
	schema = strict_object({"move_id": {"type": "integer", "minimum": 1}}, ["move_id"])

	def _move(self, ctx, args):
		moves, domain = scoped(ctx, "account.move", [("id", "=", args["move_id"])])
		move = moves.search(domain, limit=1)
		if not move:
			raise ToolDenied(ctx.env._("No such document in the agent's data."))
		if move.state != "draft":
			raise ToolDenied(ctx.env._("%s is not a draft.", move.display_name))
		return move

	def plan(self, ctx, args):
		move = self._move(ctx, args)
		return Plan(summary=ctx.env._("Post %(move)s of %(partner)s: %(amount)s", move=move.display_name,
			partner=move.partner_id.display_name or "-", amount=f"{move.amount_total:,.0f}"), amount=move.amount_total,
			model="account.move", res_ids=move.ids, company_ids=ctx.companies(move))

	def execute(self, ctx, args, plan):
		move = self._move(ctx, args)
		move.action_post()
		return {"posted": True, "document": move.name, "by": ctx.env.user.name}
