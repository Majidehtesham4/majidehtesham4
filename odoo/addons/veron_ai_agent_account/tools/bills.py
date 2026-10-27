"""A vendor bill from its file: the photo or the PDF is read (by the reading provider when one is set, or
from the text of the PDF without any AI), the vendor is found by its economic code or its name, and a
draft bill is made with the file attached. Posting is another tool, a sensitive one, that waits for a
person's approval."""

import re

from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.veron_ai_agent.services.registry import Plan, Tool, ToolDenied, tool
from odoo.addons.veron_ai_agent.services.schema import strict_object
from odoo.addons.veron_ai_agent.tools.common import scoped
from odoo.addons.veron_ai_agent.tools.documents import DOCUMENTS, INSTRUCTIONS

from ..models.petty_cash import _date, _number

_lt = LazyTranslate(__name__)
MODULE = "veron_ai_agent_account"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")
NUMBER = r"(\d{1,3}(?:[,٬]\d{3})+|\d+)(?:[.٫]\d+)?"


def text_fields(text):
	"""The fields of an Iranian invoice read from its text without a language model; what is not clear stays empty"""
	text = (text or "").translate(_DIGITS)
	lines = [line.strip() for line in text.splitlines() if line.strip()]
	fields = {"date": "", "invoice_number": "", "vendor": "", "vendor_tax_id": "", "total_amount": "", "vat_amount": "",
		"untaxed_amount": "", "confidence": "low"}
	match = re.search(r"(?:شماره\s*(?:فاکتور|صورت\s*حساب|سریال)?|invoice\s*(?:no|number|#)?)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{0,30})",
		text, re.I)
	if match:
		fields["invoice_number"] = match.group(1)
	match = re.search(r"\b(1[34]\d\d[/-]\d{1,2}[/-]\d{1,2}|20\d\d-\d{1,2}-\d{1,2})\b", text)
	if match:
		fields["date"] = match.group(1)
	match = re.search(r"(?:کد|شماره|شناسه)\s*(?:اقتصادی|ملی)\s*[:：]?\s*(\d{10,14})", text)
	if match:
		fields["vendor_tax_id"] = match.group(1)
	for line in lines:
		if re.search(r"فروشنده|نام فروشنده|seller|vendor", line, re.I):
			name = re.split(r"[:：]", line, 1)[-1].strip()
			if name and not re.search(r"فروشنده|seller|vendor", name, re.I):
				fields["vendor"] = name[:120]
				break
	if not fields["vendor"] and lines:
		fields["vendor"] = lines[0][:120]

	def amount(patterns):
		for line in lines:
			if re.search(patterns, line, re.I):
				values = [_number(v) for v in re.findall(NUMBER, line)]
				values = [v for v in values if v and v >= 1000]
				if values:
					return max(values)
		return None

	total = amount(r"جمع\s*کل|مبلغ\s*کل|قابل\s*پرداخت|جمع\s*نهایی|مبلغ\s*نهایی|(?<!sub)(?<!sub\s)total")
	vat = amount(r"ارزش\s*افزوده|مالیات|عوارض|vat|tax")
	untaxed = amount(r"جمع\s*(?:مبلغ\s*)?قبل\s*از\s*مالیات|مبلغ\s*بدون\s*مالیات|subtotal|untaxed")
	if not total:
		values = [_number(v) for v in re.findall(NUMBER, text)]
		values = [v for v in values if v and v >= 1000]
		total = max(values) if values else None
	if vat and total and vat >= total:
		vat = None
	fields.update({"total_amount": total or "", "vat_amount": vat or "", "untaxed_amount": untaxed or ""})
	return fields


@tool
class BillFromDocument(Tool):
	code = "bill_from_document"
	name = _lt("Make a Draft Vendor Bill From Its File")
	description = _lt("Reads a vendor's invoice (a photo or a PDF given to this run), finds the vendor by its economic code "
		"or its name, and makes a draft vendor bill with the file attached. Without a reading provider the text of a PDF "
		"is read. It is never posted here.")
	category = "draft"
	action = "draft"
	risk = "medium"
	module = MODULE
	models = ("account.move", "res.partner")
	schema = strict_object({"source_id": {"type": "integer", "minimum": 1, "description": "A photo or a PDF of this run"}},
		["source_id"])

	def _read(self, ctx, source):
		provider = ctx.provider("vision")
		if provider:
			result = source._extract(DOCUMENTS["invoice"], INSTRUCTIONS, provider) or {}
			values = result.get("fields") or {}
			if values.get("total_amount") or values.get("vendor"):
				values.setdefault("confidence", "medium")
				return values, provider.name
			text = result.get("text") or source.extracted_text
		elif source.kind == "pdf":
			text = source.extracted_text
		else:
			raise ToolDenied(ctx.env._("A photo is read only with a reading provider (Tesseract, Groq, Claude...). Send the "
				"invoice as a PDF, or set one in Settings, Providers."))
		if not (text or "").strip():
			raise ToolDenied(ctx.env._("No text was found in the file; it may be a scan. Set a reading provider to read it."))
		return text_fields(text), ctx.env._("text of the file")

	def plan(self, ctx, args):
		ctx.check_model("account.move")
		source = ctx.sources([args["source_id"]])
		if not source or source.kind not in ("image", "pdf"):
			raise ToolDenied(ctx.env._("The file is not a photo or a PDF of this run."))
		values, reader = self._read(ctx, source)
		total = _number(values.get("total_amount")) or 0.0
		return Plan(summary=ctx.env._("Draft vendor bill from %(file)s, %(amount)s", file=source.name, amount=f"{total:,.0f}"),
			amount=total, model="account.move", company_ids=[ctx.env.company.id],
			data={"values": values, "reader": reader})

	def _vendor(self, ctx, values):
		partners, domain = scoped(ctx, "res.partner")
		tax_id = re.sub(r"\D", "", str(values.get("vendor_tax_id") or ""))
		if tax_id:
			found = partners.search(domain & Domain("vat", "ilike", tax_id), limit=1)
			if found:
				return found
		name = str(values.get("vendor") or "").strip()
		if len(name) >= 3:
			found = partners.search(domain & Domain("name", "ilike", name), limit=10)
			exact = found.filtered(lambda p: (p.name or "").strip().lower() == name.lower())
			for candidates in (found, exact, exact.filtered(lambda p: p.supplier_rank)):
				if len(candidates) == 1:
					return candidates
		return partners.browse()

	def _account(self, ctx, vendor):
		"""The expense account of the lines: the purchase journal's, else the vendor's usual one, else the first expense"""
		journal = ctx.env["account.move"].with_context(default_move_type="in_invoice")._search_default_journal()
		account = journal.default_account_id
		if not account and vendor:
			last = ctx.env["account.move.line"].search([("partner_id", "=", vendor.id), ("move_id.move_type", "=", "in_invoice"),
				("display_type", "=", "product"), ("parent_state", "=", "posted")], order="id desc", limit=1)
			account = last.account_id
		if not account:
			account = ctx.env["account.account"].search([("account_type", "=", "expense"), ("active", "=", True),
				*ctx.env["account.account"]._check_company_domain(ctx.env.company)], limit=1)
		if not account:
			raise ToolDenied(ctx.env._("No expense account was found; set the default account of the purchase journal."))
		return account

	def _tax(self, ctx, untaxed, vat):
		if not untaxed or not vat:
			return ctx.env["account.tax"]
		rate = round(vat / untaxed * 100, 1)
		taxes = ctx.env["account.tax"].search([("type_tax_use", "=", "purchase"), ("amount_type", "=", "percent"),
			("company_id", "=", ctx.env.company.id)])
		return taxes.filtered(lambda t: abs(t.amount - rate) < 0.6)[:1]

	def execute(self, ctx, args, plan):
		source = ctx.sources([args["source_id"]])
		values = plan.data["values"]
		vendor = self._vendor(ctx, values)
		number = str(values.get("invoice_number") or "").strip()[:60]
		if vendor and number:
			moves, domain = scoped(ctx, "account.move", [("move_type", "=", "in_invoice"), ("ref", "=", number),
				("commercial_partner_id", "=", vendor.commercial_partner_id.id), ("state", "!=", "cancel")])
			twin = moves.search(domain, limit=1)
			if twin:
				raise ToolDenied(ctx.env._("This invoice is already recorded as %s.", twin.display_name))
		total = _number(values.get("total_amount")) or 0.0
		vat = _number(values.get("vat_amount")) or 0.0
		untaxed = _number(values.get("untaxed_amount")) or (total - vat if total else 0.0)
		tax = self._tax(ctx, untaxed, vat)
		label = ctx.env._("Invoice %(number)s of %(vendor)s", number=number or "-",
			vendor=vendor.name or values.get("vendor") or "-")
		lines = []
		for line in values.get("lines") or []:
			price = _number(line.get("unit_price"))
			quantity = _number(line.get("quantity")) or 1.0
			if line.get("description") and price:
				lines.append((0, 0, {"name": str(line["description"])[:250], "quantity": quantity, "price_unit": price,
					"tax_ids": [(6, 0, tax.ids)]}))
		if not lines or (untaxed and abs(sum(l[2]["quantity"] * l[2]["price_unit"] for l in lines) - untaxed) > 1):
			lines = [(0, 0, {"name": label, "quantity": 1, "price_unit": untaxed if tax else total, "tax_ids": [(6, 0, tax.ids)]})]
		account = self._account(ctx, vendor)
		for line in lines:
			line[2]["account_id"] = account.id
		move_values = {"move_type": "in_invoice", "partner_id": vendor.id or False, "ref": number or False,
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
		if not vendor:
			checks.append(ctx.env._("The vendor «%s» was not found; choose it on the bill.", values.get("vendor") or "-"))
		if vat and not tax:
			checks.append(ctx.env._("No purchase tax of this rate was found; the VAT is inside the amount."))
		if values.get("confidence") == "low":
			checks.append(ctx.env._("Read with low confidence; compare the bill with the file."))
		return {"draft_id": move.id, "draft": move.display_name, "vendor": vendor.display_name or None,
			"number": number or None, "date": str(date) if date else None, "untaxed": round(move.amount_untaxed, 2),
			"tax": round(move.amount_tax, 2), "total": round(move.amount_total, 2), "read_by": plan.data.get("reader"),
			"to_check": checks, "posted": False}


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
