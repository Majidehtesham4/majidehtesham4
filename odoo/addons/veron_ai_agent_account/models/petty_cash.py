"""Petty cash: a fund held by a custodian, closed period by period. The custodian gives the receipts of a
period (photos or PDFs, checked when they come in), confirms what was read from them, the receipts are
checked for duplicates and against the fund's policy, a person decides what needs review, a draft entry
is made from the accepted receipts and posted only by a person with the right to post.

Balances come from posted journal items of the fund's account and the custodian, never from an estimate."""

import base64
import hashlib
import json
import re
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.veron_ai_agent.services import files as filetools
from odoo.addons.veron_core.models import jalali

CLOSING_STATES = [
	("draft", "Collecting Documents"),
	("review", "In Review"),
	("to_approve", "Waiting for Approval"),
	("posted", "Posted"),
	("cancelled", "Cancelled"),
]
RECEIPT_STATES = [
	("new", "New"),
	("extracted", "Read, to Confirm"),
	("confirmed", "Confirmed by the Custodian"),
	("accepted", "Accepted in Review"),
	("review", "Needs a Person's Review"),
	("rejected", "Not Accepted"),
]
ISSUE_KINDS = [
	("duplicate_file", "Same File"),
	("duplicate_image", "Similar Photo"),
	("duplicate_number", "Same Vendor and Number"),
	("duplicate_amount", "Same Vendor, Date and Amount"),
	("amount", "Amount"),
	("date", "Date"),
	("limit", "Over the Limit"),
	("category", "Expense Type"),
	("tax_id", "Vendor's Tax ID"),
	("reading", "Reading"),
]
# Data fields of a receipt the custodian fills or corrects; the decision fields are not among them
RECEIPT_DATA = {"date", "vendor_name", "partner_id", "vendor_tax_id", "receipt_number", "amount", "vat_amount",
	"description", "category_id", "upload", "upload_name"}


def shamsi(value):
	if not value:
		return ""
	year, month, day = jalali.to_jalali(value)
	return f"{year}/{month:02d}/{day:02d}"


def _norm(text):
	return re.sub(r"\s+", " ", (text or "").strip().replace("ي", "ی").replace("ك", "ک")).lower()


def _is_accountant(user):
	return user.has_group("account.group_account_user") or user.has_group("account.group_account_manager")


class PettyCashCategory(models.Model):
	_name = "veron.petty.cash.category"
	_description = "Petty Cash Expense Type"
	_order = "sequence, name"
	_check_company_auto = True

	name = fields.Char(required=True, translate=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	account_id = fields.Many2one("account.account", "Expense Account", required=True, check_company=True,
		domain=[("account_type", "in", ("expense", "expense_direct_cost", "expense_other"))])
	max_amount = fields.Monetary("Highest Amount of a Receipt", currency_field="currency_id",
		help="Empty: the limit of the fund")
	needs_tax_id = fields.Boolean("Needs the Vendor's Tax ID", help="An official invoice with the vendor's economic code")
	currency_id = fields.Many2one(related="company_id.currency_id")
	note = fields.Char()


class PettyCashFund(models.Model):
	_name = "veron.petty.cash.fund"
	_description = "Petty Cash Fund"
	_inherit = ["mail.thread"]
	_order = "name"
	_check_company_auto = True

	name = fields.Char(required=True, tracking=True)
	active = fields.Boolean(default=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
	currency_id = fields.Many2one(related="company_id.currency_id")
	custodian_user_id = fields.Many2one("res.users", "Custodian", required=True, tracking=True,
		domain=[("share", "=", False)])
	custodian_partner_id = fields.Many2one(related="custodian_user_id.partner_id", store=True, string="Custodian Contact")
	account_id = fields.Many2one("account.account", "Petty Cash Account", required=True, check_company=True,
		tracking=True, domain=[("account_type", "in", ("asset_cash", "asset_current", "asset_receivable"))],
		help="The account of the money in the custodian's hands, e.g. 111003 Petty cash; its items carry the custodian")
	journal_id = fields.Many2one("account.journal", "Journal", required=True, check_company=True,
		domain=[("type", "=", "general")], help="The journal of the settlement entries")
	amount = fields.Monetary("Fund Amount", currency_field="currency_id", tracking=True)
	max_receipt_amount = fields.Monetary("Highest Amount of a Receipt", currency_field="currency_id", tracking=True)
	max_receipt_age_days = fields.Integer("Oldest Receipt (Days Before the Period)", default=30)
	tax_id_required_above = fields.Monetary("Tax ID Needed Above", currency_field="currency_id",
		help="Receipts above this amount need the vendor's tax ID; empty: never by amount")
	vat_account_id = fields.Many2one("account.account", "Input VAT Account", check_company=True,
		help="When set, the VAT of a receipt with the vendor's tax ID is put on this account")
	category_ids = fields.Many2many("veron.petty.cash.category", string="Allowed Expense Types", check_company=True,
		help="Empty: every expense type of the company")
	similar_distance = fields.Integer("Photo Likeness", default=6,
		help="How alike two photos must be to be shown as similar: 0 identical, 10 loosely alike")
	closing_ids = fields.One2many("veron.petty.cash.closing", "fund_id", "Closings")
	balance = fields.Monetary(compute="_compute_balance", currency_field="currency_id",
		help="Posted journal items of the account for the custodian")

	@api.model_create_multi
	def create(self, vals_list):
		funds = super().create(vals_list)
		funds._add_custodians()
		return funds

	def write(self, vals):
		res = super().write(vals)
		if "custodian_user_id" in vals:
			self._add_custodians()
		return res

	def _add_custodians(self):
		group = self.env.ref("veron_ai_agent_account.group_petty_cash_custodian")
		group.sudo().write({"user_ids": [(4, user.id) for user in self.custodian_user_id]})

	@api.depends("account_id", "custodian_partner_id")
	def _compute_balance(self):
		for fund in self:
			fund.balance = fund._balance()

	def _items(self):
		self.ensure_one()
		return Domain([("account_id", "=", self.account_id.id), ("partner_id", "=", self.custodian_partner_id.id),
			("parent_state", "=", "posted"), ("company_id", "=", self.company_id.id)])

	def _balance(self, before=None):
		"""The posted balance in the custodian's hands, before a date when given"""
		self.ensure_one()
		if not self.account_id:
			return 0.0
		domain = self._items()
		if before:
			domain &= Domain("date", "<", before)
		rows = self.env["account.move.line"].sudo()._read_group(domain, [], ["balance:sum"])
		return rows[0][0] or 0.0

	def _topups(self, date_from, date_to):
		"""Money given to the custodian in the period: debits of the account, settlements excluded"""
		self.ensure_one()
		settled = self.closing_ids.move_id.ids
		domain = self._items() & Domain([("date", ">=", date_from), ("date", "<=", date_to), ("debit", ">", 0),
			("move_id", "not in", settled)])
		rows = self.env["account.move.line"].sudo()._read_group(domain, [], ["debit:sum"])
		return rows[0][0] or 0.0

	def _next_start(self):
		self.ensure_one()
		last = self.closing_ids.filtered(lambda c: c.state != "cancelled").sorted("date_to")[-1:]
		return (last.date_to + timedelta(days=1)) if last else fields.Date.context_today(self).replace(day=1)


class PettyCashClosing(models.Model):
	_name = "veron.petty.cash.closing"
	_description = "Petty Cash Closing"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "date_to desc, id desc"
	_check_company_auto = True

	name = fields.Char(readonly=True, default="/", copy=False)
	fund_id = fields.Many2one("veron.petty.cash.fund", required=True, index=True, check_company=True, tracking=True)
	company_id = fields.Many2one(related="fund_id.company_id", store=True, index=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	custodian_user_id = fields.Many2one(related="fund_id.custodian_user_id", store=True)
	date_from = fields.Date("From", required=True)
	date_to = fields.Date("To", required=True)
	period = fields.Char(compute="_compute_period")
	state = fields.Selection(CLOSING_STATES, default="draft", required=True, readonly=True, tracking=True, index=True)
	receipt_ids = fields.One2many("veron.petty.cash.receipt", "closing_id", "Receipts")
	receipt_count = fields.Integer(compute="_compute_amounts")
	opening_balance = fields.Monetary(compute="_compute_amounts", currency_field="currency_id")
	topup_amount = fields.Monetary("Given in the Period", compute="_compute_amounts", currency_field="currency_id")
	submitted_amount = fields.Monetary("Receipts Given", compute="_compute_amounts", currency_field="currency_id")
	accepted_amount = fields.Monetary("Accepted", compute="_compute_amounts", currency_field="currency_id")
	rejected_amount = fields.Monetary("Not Accepted", compute="_compute_amounts", currency_field="currency_id")
	review_amount = fields.Monetary("To Review", compute="_compute_amounts", currency_field="currency_id")
	closing_balance = fields.Monetary(compute="_compute_amounts", currency_field="currency_id",
		help="Opening balance, plus what was given, less the accepted receipts")
	issue_count = fields.Integer(compute="_compute_amounts")
	move_id = fields.Many2one("account.move", "Settlement Entry", readonly=True, copy=False)
	move_state = fields.Selection(related="move_id.state", string="Entry State")
	draft_signature = fields.Char(readonly=True, copy=False)
	requested_at = fields.Datetime("Documents Asked On", readonly=True, copy=False)
	submitted_at = fields.Datetime("Documents Given On", readonly=True, copy=False)
	posted_by = fields.Many2one("res.users", readonly=True, copy=False)
	report_attachment_id = fields.Many2one("ir.attachment", "Settlement Report", readonly=True, copy=False)
	note = fields.Text()

	@api.depends("date_from", "date_to")
	def _compute_period(self):
		for closing in self:
			closing.period = f"{shamsi(closing.date_from)} - {shamsi(closing.date_to)}"

	@api.depends("receipt_ids.amount", "receipt_ids.state", "fund_id", "date_from", "date_to")
	def _compute_amounts(self):
		for closing in self:
			receipts = closing.receipt_ids
			closing.receipt_count = len(receipts)
			closing.submitted_amount = sum(receipts.mapped("amount"))
			closing.accepted_amount = sum(receipts.filtered(lambda r: r.state == "accepted").mapped("amount"))
			closing.rejected_amount = sum(receipts.filtered(lambda r: r.state == "rejected").mapped("amount"))
			closing.review_amount = sum(receipts.filtered(lambda r: r.state not in ("accepted", "rejected")).mapped("amount"))
			closing.issue_count = len(receipts.issue_ids.filtered(lambda i: not i.resolved))
			if closing.fund_id and closing.date_from and closing.date_to:
				closing.opening_balance = closing.fund_id._balance(before=closing.date_from)
				closing.topup_amount = closing.fund_id._topups(closing.date_from, closing.date_to)
			else:
				closing.opening_balance = closing.topup_amount = 0.0
			closing.closing_balance = closing.opening_balance + closing.topup_amount - closing.accepted_amount

	@api.constrains("date_from", "date_to", "fund_id", "state")
	def _check_dates(self):
		for closing in self:
			if closing.date_from > closing.date_to:
				raise ValidationError(_("The period starts before it ends."))
			overlap = self.search_count([("id", "!=", closing.id), ("fund_id", "=", closing.fund_id.id),
				("state", "!=", "cancelled"), ("date_from", "<=", closing.date_to), ("date_to", ">=", closing.date_from)])
			if overlap and closing.state != "cancelled":
				raise ValidationError(_("Another closing of %s covers part of this period.", closing.fund_id.name))

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", "/") == "/":
				vals["name"] = self.env["ir.sequence"].sudo().next_by_code("veron.petty.cash.closing") or "/"
		return super().create(vals_list)

	def write(self, vals):
		if not self.env.su and not _is_accountant(self.env.user):
			refused = [key for key in vals if key != "note" and not key.startswith(("message_", "activity_"))]
			if refused:
				raise AccessError(_("A closing changes through its steps; the custodian writes only notes."))
		return super().write(vals)

	def _shamsi(self, value):
		return shamsi(value)

	def _check_accountant(self):
		if not _is_accountant(self.env.user):
			raise AccessError(_("Only an accountant does this."))

	# --- the steps

	def _request_documents(self):
		"""Step 1: the custodian is asked for the receipts of the period"""
		for closing in self.filtered(lambda c: c.state == "draft"):
			closing.activity_schedule("mail.mail_activity_data_todo", user_id=closing.custodian_user_id.id,
				summary=_("Receipts of petty cash %(fund)s, %(period)s", fund=closing.fund_id.name, period=closing.period),
				note=Markup("<p>%s</p>") % _("Add a photo or a PDF of each receipt of the period, check what was read "
					"from it, confirm it, then press «Documents Given»."))
			closing.requested_at = fields.Datetime.now()
		return True

	def action_submit(self):
		"""The custodian has given the documents of the period"""
		for closing in self:
			if closing.state != "draft":
				raise UserError(_("The documents of %s are already given.", closing.name))
			if self.env.user != closing.custodian_user_id and not _is_accountant(self.env.user):
				raise AccessError(_("The custodian or an accountant gives the documents."))
			if not closing.receipt_ids:
				raise UserError(_("Add the receipts first."))
			unconfirmed = closing.receipt_ids.filtered(lambda r: r.state in ("new", "extracted"))
			if unconfirmed:
				raise UserError(_("Confirm each receipt first: %s", ", ".join(unconfirmed.mapped("display_name"))))
			closing.sudo().write({"state": "review", "submitted_at": fields.Datetime.now()})
			closing.activity_ids.filtered(lambda a: a.user_id == closing.custodian_user_id).action_feedback(_("Given"))
		return True

	def _review(self):
		"""Steps 5 to 7: each confirmed receipt is checked; without a finding it is accepted in the review,
		with one it waits for a person"""
		self.ensure_one()
		results = {"accepted": [], "review": [], "waiting": []}
		for receipt in self.receipt_ids:
			if receipt.state in ("new", "extracted"):
				results["waiting"].append(receipt)
				continue
			if receipt.state in ("rejected",) or (receipt.state in ("accepted", "review") and receipt.decided_by):
				continue
			issues = receipt._check()
			receipt.sudo().state = "review" if issues else "accepted"
			results["review" if issues else "accepted"].append(receipt)
		return results

	def _signature(self):
		accepted = self.receipt_ids.filtered(lambda r: r.state == "accepted").sorted("id")
		data = [(r.id, r.amount, r.vat_amount, r.account_id.id, r.vendor_tax_id or "") for r in accepted]
		return hashlib.sha256(json.dumps(data).encode()).hexdigest()

	def _draft_move(self):
		"""Step 8: the draft settlement entry of the accepted receipts; it is not posted here"""
		self.ensure_one()
		if self.state not in ("review", "to_approve"):
			raise UserError(_("The entry is made after the documents are given and reviewed."))
		pending = self.receipt_ids.filtered(lambda r: r.state not in ("accepted", "rejected"))
		if pending:
			raise UserError(_("%s receipts wait for a person's review or the custodian's confirmation.", len(pending)))
		accepted = self.receipt_ids.filtered(lambda r: r.state == "accepted")
		if not accepted:
			raise UserError(_("No receipt is accepted; there is nothing to settle."))
		if self.move_id and self.move_id.state == "posted":
			raise UserError(_("The entry of %s is already posted.", self.name))
		fund = self.fund_id
		lines = []
		for receipt in accepted:
			if not receipt.account_id:
				raise UserError(_("%s has no expense account; choose its expense type.", receipt.display_name))
			label = " - ".join(filter(None, [receipt.vendor_name or receipt.partner_id.name, receipt.receipt_number,
				receipt.description]))[:250] or receipt.display_name
			vat = receipt.vat_amount if (fund.vat_account_id and receipt.vat_amount and receipt.vendor_tax_id) else 0.0
			lines.append((0, 0, {"account_id": receipt.account_id.id, "name": label, "debit": receipt.amount - vat,
				"partner_id": receipt.partner_id.id or False}))
			if vat:
				lines.append((0, 0, {"account_id": fund.vat_account_id.id, "name": _("VAT of %s", label), "debit": vat,
					"partner_id": receipt.partner_id.id or False}))
		total = sum(accepted.mapped("amount"))
		lines.append((0, 0, {"account_id": fund.account_id.id, "partner_id": fund.custodian_partner_id.id, "credit": total,
			"name": _("Settlement of petty cash %(fund)s, %(period)s", fund=fund.name, period=self.period)}))
		values = {"move_type": "entry", "journal_id": fund.journal_id.id, "date": self.date_to, "ref": self.name,
			"line_ids": lines, "company_id": self.company_id.id}
		if self.move_id and self.move_id.state == "draft":
			self.move_id.line_ids.unlink()
			self.move_id.write(values)
			move = self.move_id
		else:
			move = self.env["account.move"].create(values)
		# The files of the receipts go with the entry
		for receipt in accepted.filtered("source_id"):
			source = receipt.source_id.sudo()
			if source.attachment_id:
				source.attachment_id.copy({"res_model": "account.move", "res_id": move.id, "name": f"{receipt.name} - {source.name}"})
		self.sudo().write({"move_id": move.id, "state": "to_approve", "draft_signature": self._signature()})
		return move

	def _post(self):
		"""Step 10: posted by the person who approved it, with that person's own rights"""
		self.ensure_one()
		if self.state != "to_approve" or not self.move_id or self.move_id.state != "draft":
			raise UserError(_("%s has no draft entry waiting for approval.", self.name))
		if self.draft_signature != self._signature():
			raise UserError(_("The receipts changed after the draft entry was made; make the entry again."))
		if not self.env.user.has_group("account.group_account_invoice"):
			raise AccessError(_("You may not post accounting entries."))
		self.move_id.with_env(self.env).action_post()
		self.sudo().write({"state": "posted", "posted_by": self.env.uid})
		self.message_post(body=_("Posted by %s.", self.env.user.name))
		return self.move_id

	def _make_report(self):
		"""Step 11: the settlement report, kept on the closing"""
		self.ensure_one()
		pdf, _type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
			"veron_ai_agent_account.action_report_settlement", self.ids)
		attachment = self.env["ir.attachment"].sudo().create({"name": f"{self.name}.pdf", "raw": pdf,
			"mimetype": "application/pdf", "res_model": self._name, "res_id": self.id})
		self.sudo().report_attachment_id = attachment
		return attachment

	def _figures(self):
		self.ensure_one()
		receipts = self.receipt_ids
		return {
			"closing": self.name, "fund": self.fund_id.name, "custodian": self.custodian_user_id.name,
			"period": self.period, "state": dict(CLOSING_STATES)[self.state],
			"opening_balance": self.opening_balance, "given_in_period": self.topup_amount,
			"receipts": len(receipts), "receipts_amount": self.submitted_amount,
			"accepted": len(receipts.filtered(lambda r: r.state == "accepted")), "accepted_amount": self.accepted_amount,
			"not_accepted": len(receipts.filtered(lambda r: r.state == "rejected")), "not_accepted_amount": self.rejected_amount,
			"to_review": len(receipts.filtered(lambda r: r.state not in ("accepted", "rejected"))),
			"to_review_amount": self.review_amount, "closing_balance": self.closing_balance,
			"entry": self.move_id.name if self.move_id else None, "entry_state": self.move_id.state if self.move_id else None,
			"open_findings": self.issue_count, "currency": self.currency_id.name,
		}

	# --- buttons of people

	def action_request_documents(self):
		self._check_accountant()
		return self._request_documents()

	def action_review(self):
		self._check_accountant()
		for closing in self:
			if closing.state == "draft":
				raise UserError(_("The custodian gives the documents first."))
			closing._review()
		return True

	def action_draft_move(self):
		self._check_accountant()
		self.ensure_one()
		move = self._draft_move()
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": move.id, "view_mode": "form"}

	def action_post(self):
		"""A person with the right to post may post the checked draft directly, without an agent"""
		self._check_accountant()
		for closing in self:
			closing._post()
		return True

	def action_print(self):
		return self.env.ref("veron_ai_agent_account.action_report_settlement").report_action(self)

	def action_cancel(self):
		self._check_accountant()
		for closing in self:
			if closing.state == "posted":
				raise UserError(_("A posted closing is undone by reversing its entry in accounting."))
			if closing.move_id and closing.move_id.state == "draft":
				closing.move_id.button_cancel()
			closing.sudo().state = "cancelled"
		return True

	def action_open_move(self):
		self.ensure_one()
		return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.move_id.id, "view_mode": "form"}


class PettyCashReceipt(models.Model):
	_name = "veron.petty.cash.receipt"
	_description = "Petty Cash Receipt"
	_inherit = ["mail.thread"]
	_order = "closing_id, date, id"
	_check_company_auto = True

	name = fields.Char(readonly=True, default="/", copy=False)
	closing_id = fields.Many2one("veron.petty.cash.closing", required=True, index=True, ondelete="cascade", check_company=True)
	fund_id = fields.Many2one(related="closing_id.fund_id", store=True, index=True)
	company_id = fields.Many2one(related="closing_id.company_id", store=True, index=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	closing_state = fields.Selection(related="closing_id.state", string="Closing State")
	source_id = fields.Many2one("veron.ai.source", "File", readonly=True, ondelete="restrict")
	sha256 = fields.Char(related="source_id.sha256", store=True, index=True)
	dhash = fields.Char(related="source_id.dhash", store=True)
	upload = fields.Binary("Photo or PDF", compute="_compute_upload", inverse="_inverse_upload")
	upload_name = fields.Char(compute="_compute_upload", inverse="_inverse_upload")
	date = fields.Date(tracking=True)
	vendor_name = fields.Char("Vendor", tracking=True)
	partner_id = fields.Many2one("res.partner", "Vendor in Odoo", check_company=True)
	vendor_tax_id = fields.Char("Vendor's Tax ID")
	receipt_number = fields.Char("Number")
	amount = fields.Monetary(currency_field="currency_id", tracking=True)
	vat_amount = fields.Monetary("VAT", currency_field="currency_id")
	description = fields.Char()
	category_id = fields.Many2one("veron.petty.cash.category", "Expense Type", check_company=True)
	account_id = fields.Many2one("account.account", compute="_compute_account", store=True, readonly=False,
		check_company=True)
	extracted_json = fields.Text("Read from the File", readonly=True)
	confidence = fields.Selection([("low", "Low"), ("medium", "Medium"), ("high", "High")], readonly=True)
	state = fields.Selection(RECEIPT_STATES, default="new", required=True, readonly=True, tracking=True, index=True)
	confirmed_by = fields.Many2one("res.users", readonly=True)
	confirmed_at = fields.Datetime(readonly=True)
	decided_by = fields.Many2one("res.users", "Reviewed By", readonly=True)
	decision_note = fields.Char("Review Note")
	issue_ids = fields.One2many("veron.petty.cash.issue", "receipt_id", "Findings")
	open_issue_count = fields.Integer(compute="_compute_open_issue_count")

	def _compute_upload(self):
		for receipt in self:
			receipt.upload = False
			receipt.upload_name = receipt.source_id.name or False

	def _inverse_upload(self):
		for receipt in self.filtered("upload"):
			receipt._attach(receipt.upload_name or "receipt", base64.b64decode(receipt.upload))

	def _attach(self, name, data):
		"""A file of the receipt, checked by its content (type, size, antivirus) before it is kept"""
		self.ensure_one()
		source = self.env["veron.ai.source"]._from_upload(name, data, purpose="receipt", kinds=("image", "pdf"), record=self)
		self.sudo().write({"source_id": source.id, "state": "new", "extracted_json": False})
		return source

	@api.depends("category_id")
	def _compute_account(self):
		for receipt in self:
			receipt.account_id = receipt.category_id.account_id or receipt.account_id

	def _compute_open_issue_count(self):
		for receipt in self:
			receipt.open_issue_count = len(receipt.issue_ids.filtered(lambda i: not i.resolved))

	@api.depends("name", "vendor_name", "amount")
	def _compute_display_name(self):
		for receipt in self:
			parts = [receipt.name, receipt.vendor_name or receipt.partner_id.name]
			receipt.display_name = " - ".join(p for p in parts if p and p != "/") or _("Receipt")

	@api.model_create_multi
	def create(self, vals_list):
		custodian = not self.env.su and not _is_accountant(self.env.user)
		for vals in vals_list:
			if custodian:
				if set(vals) - RECEIPT_DATA - {"closing_id", "source_id", "name"}:
					raise AccessError(_("The custodian gives the data of a receipt; an accountant reviews it."))
				if vals.get("source_id"):
					self.env["veron.ai.source"].browse(vals["source_id"]).check_access("read")
			if vals.get("name", "/") == "/":
				vals["name"] = self.env["ir.sequence"].sudo().next_by_code("veron.petty.cash.receipt") or "/"
		receipts = super().create(vals_list)
		for receipt in receipts:
			receipt._check_editable()
		return receipts

	def write(self, vals):
		if not self.env.su and not _is_accountant(self.env.user):
			refused = set(vals) - RECEIPT_DATA
			if refused:
				raise AccessError(_("The custodian changes only the data of a receipt; an accountant reviews it."))
			self._check_editable()
		res = super().write(vals)
		if RECEIPT_DATA & set(vals) and not self.env.context.get("veron_keep_state"):
			# Changed data is confirmed and checked again
			self.filtered(lambda r: r.state in ("confirmed", "accepted", "review") and not r.decided_by).sudo().with_context(
				veron_keep_state=True).write({"state": "extracted"})
		return res

	def _check_editable(self):
		for receipt in self:
			if receipt.closing_id.state not in ("draft", "review") and not self.env.su:
				raise UserError(_("The receipts of %s are not changed any more.", receipt.closing_id.name))

	# --- reading the file

	def _extract(self, provider=None):
		"""Step 3: the fields read from the file by the vision provider, for the custodian to check"""
		from odoo.addons.veron_ai_agent.tools.documents import DOCUMENTS, INSTRUCTIONS

		self.ensure_one()
		if not self.source_id:
			return None
		result = self.source_id._extract(DOCUMENTS["receipt"], INSTRUCTIONS, provider)
		if result is None:
			return None
		values = result.get("fields") or {}
		update = {"extracted_json": json.dumps(values, ensure_ascii=False), "state": "extracted",
			"confidence": values.get("confidence") if values.get("confidence") in ("low", "medium", "high") else False}
		amount = _number(values.get("amount"))
		if amount and not self.amount:
			update["amount"] = amount
		vat = _number(values.get("vat_amount"))
		if vat and not self.vat_amount:
			update["vat_amount"] = vat
		date = _date(values.get("date"))
		if date and not self.date:
			update["date"] = date
		for field, key in (("vendor_name", "vendor"), ("receipt_number", "receipt_number"), ("vendor_tax_id", "vendor_tax_id"),
				("description", "description")):
			if values.get(key) and not self[field]:
				update[field] = str(values[key])[:200]
		self.sudo().with_context(veron_keep_state=True).write(update)
		return values

	# --- the custodian and the accountant

	def action_confirm(self):
		"""Step 4: the custodian confirms what the receipt says"""
		for receipt in self:
			if self.env.user != receipt.closing_id.custodian_user_id and not _is_accountant(self.env.user):
				raise AccessError(_("The custodian confirms the receipts."))
			receipt._check_editable()
			if not receipt.amount or receipt.amount <= 0 or not receipt.date:
				raise UserError(_("Enter the date and the amount of %s first.", receipt.display_name))
			receipt.sudo().with_context(veron_keep_state=True).write({"state": "confirmed", "confirmed_by": self.env.uid,
				"confirmed_at": fields.Datetime.now()})
		return True

	def action_accept(self):
		self._decide("accepted")
		return True

	def action_reject(self):
		self._decide("rejected")
		return True

	def _decide(self, state):
		if not _is_accountant(self.env.user) or self.env.context.get("veron_ai_run_id"):
			raise AccessError(_("An accountant reviews the receipts; an agent does not."))
		for receipt in self:
			if receipt.state in ("new", "extracted"):
				raise UserError(_("The custodian confirms %s first.", receipt.display_name))
			receipt._check_editable()
			receipt.sudo().with_context(veron_keep_state=True).write({"state": state, "decided_by": self.env.uid})
			receipt.issue_ids.filtered(lambda i: not i.resolved).sudo().write({"resolved": True, "resolved_by": self.env.uid,
				"resolution": receipt.decision_note or dict(RECEIPT_STATES)[state]})

	def action_check(self):
		for receipt in self:
			receipt._check()
		return True

	def action_open_file(self):
		self.ensure_one()
		if not self.source_id:
			raise UserError(_("This receipt has no file."))
		return self.source_id.action_download()

	# --- the checks

	def _check(self):
		"""Steps 5 and 6: duplicates and the fund's policy. The findings are written plainly: a likeness is
		something to check, not a fault of anyone."""
		self.ensure_one()
		fund = self.fund_id
		closing = self.closing_id
		found = []

		def add(kind, message, severity="warning", other=None):
			found.append({"kind": kind, "message": message, "severity": severity, "other_receipt_id": other.id if other else False})

		Receipt = self.sudo()
		others = Domain([("id", "!=", self.id), ("company_id", "=", self.company_id.id)])
		if self.sha256:
			same = Receipt.search(others & Domain("sha256", "=", self.sha256), limit=1)
			if same:
				add("duplicate_file", _("This file is the same as the file of receipt %(other)s (%(closing)s); please check.",
					other=same.name, closing=same.closing_id.name), "critical", same)
		if self.dhash:
			for other in Receipt.search(others & Domain([("dhash", "!=", False), ("sha256", "!=", self.sha256 or "-")]),
					limit=2000):
				if filetools.hamming(self.dhash, other.dhash) <= fund.similar_distance:
					add("duplicate_image", _("This photo looks like the photo of receipt %(other)s (%(closing)s); please check "
						"they are two different receipts.", other=other.name, closing=other.closing_id.name), "warning", other)
					break
		vendor = _norm(self.vendor_name or self.partner_id.name)
		if vendor and self.receipt_number:
			for other in Receipt.search(others & Domain("receipt_number", "=", self.receipt_number), limit=50):
				if _norm(other.vendor_name or other.partner_id.name) == vendor:
					add("duplicate_number", _("Receipt %(other)s has the same vendor and number; please check.",
						other=other.name), "critical", other)
					break
		if vendor and self.date and self.amount:
			for other in Receipt.search(others & Domain([("date", "=", self.date), ("amount", "=", self.amount)]), limit=50):
				if _norm(other.vendor_name or other.partner_id.name) == vendor:
					add("duplicate_amount", _("Receipt %(other)s has the same vendor, date and amount; please check.",
						other=other.name), "warning", other)
					break
		if not self.amount or self.amount <= 0:
			add("amount", _("The amount is missing."), "critical")
		if self.vat_amount and self.vat_amount > self.amount:
			add("amount", _("The VAT is more than the amount."), "critical")
		if not self.date:
			add("date", _("The date is missing."))
		elif closing.date_to and (self.date > closing.date_to or (fund.max_receipt_age_days and
				(closing.date_from - self.date).days > fund.max_receipt_age_days)):
			add("date", _("The date %(date)s is outside the period %(period)s.", date=shamsi(self.date), period=closing.period))
		limit = self.category_id.max_amount or fund.max_receipt_amount
		if limit and self.amount > limit:
			add("limit", _("The amount is over the limit of %(limit)s; a person decides.", limit=f"{limit:,.0f}"))
		if not self.category_id:
			add("category", _("The expense type is not chosen."))
		elif fund.category_ids and self.category_id not in fund.category_ids:
			add("category", _("%s is not an expense type of this fund.", self.category_id.name))
		needs_tax_id = self.category_id.needs_tax_id or (fund.tax_id_required_above and self.amount > fund.tax_id_required_above)
		if needs_tax_id and not self.vendor_tax_id:
			add("tax_id", _("The vendor's tax ID (economic code) is needed for this receipt."))
		if self.confidence == "low":
			add("reading", _("The file was read with low confidence; compare the fields with the file."))
		Issue = self.env["veron.petty.cash.issue"].sudo()
		self.issue_ids.filtered(lambda i: not i.resolved).sudo().unlink()
		for values in found:
			Issue.create({"receipt_id": self.id, **values})
		return found


class PettyCashIssue(models.Model):
	_name = "veron.petty.cash.issue"
	_description = "Petty Cash Finding"
	_order = "resolved, severity desc, id"

	receipt_id = fields.Many2one("veron.petty.cash.receipt", required=True, index=True, ondelete="cascade")
	closing_id = fields.Many2one(related="receipt_id.closing_id", store=True, index=True)
	company_id = fields.Many2one(related="receipt_id.company_id", store=True, index=True)
	kind = fields.Selection(ISSUE_KINDS, required=True)
	severity = fields.Selection([("warning", "To Check"), ("critical", "Important")], default="warning", required=True)
	message = fields.Char(required=True)
	other_receipt_id = fields.Many2one("veron.petty.cash.receipt", "Similar Receipt", ondelete="set null")
	resolved = fields.Boolean(readonly=True)
	resolved_by = fields.Many2one("res.users", readonly=True)
	resolution = fields.Char(readonly=True)


def _number(value):
	"""Digits of an amount as written, Persian or Arabic digits included; None when there are none"""
	if value in (None, "", False):
		return None
	if isinstance(value, (int, float)):
		return float(value)
	text = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
	digits = re.sub(r"[^\d.]", "", text.replace("٫", "."))
	try:
		return float(digits) if digits else None
	except ValueError:
		return None


def _date(value):
	"""A date written as YYYY-MM-DD, or a Shamsi date as 1405/08/05; None when it is not clear"""
	if not value:
		return None
	text = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
	match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
	if not match:
		return None
	year, month, day = (int(g) for g in match.groups())
	try:
		if 1300 <= year <= 1500:
			return jalali.to_gregorian(year, month, day)
		return fields.Date.to_date(f"{year:04d}-{month:02d}-{day:02d}")
	except (ValueError, TypeError):
		return None
