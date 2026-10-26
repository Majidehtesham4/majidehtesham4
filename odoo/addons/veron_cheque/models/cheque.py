"""A cheque and its steps; each step posts the accounting entry that moves the cheque from one
account to the next, and the lines on reconcilable accounts are matched as the cheque leaves them."""

import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

IN_STATES = [("draft", "Draft"), ("hand", "In Hand"), ("collection", "In Collection"), ("cashed", "Cashed"),
	("bounced", "Bounced"), ("returned", "Returned to Customer"), ("endorsed", "Endorsed")]
OUT_STATES = [("issued", "Issued"), ("cancelled", "Cancelled")]


class ChequeBook(models.Model):
	_name = "veron.cheque.book"
	_description = "Cheque Book"

	name = fields.Char(required=True)
	journal_id = fields.Many2one("account.journal", "Bank", required=True, domain="[('type', '=', 'bank')]")
	first_serial = fields.Integer("First Serial", required=True)
	sheets = fields.Integer("Sheets", default=25, required=True)
	cheque_ids = fields.One2many("veron.cheque", "book_id")
	next_serial = fields.Integer(compute="_compute_next_serial")
	remaining = fields.Integer(compute="_compute_next_serial")
	company_id = fields.Many2one(related="journal_id.company_id", store=True)
	active = fields.Boolean(default=True)

	@api.depends("cheque_ids.serial", "first_serial", "sheets")
	def _compute_next_serial(self):
		for book in self:
			used = {int(s) for s in book.cheque_ids.mapped("serial") if s and s.isdigit()}
			free = [n for n in range(book.first_serial, book.first_serial + book.sheets) if n not in used]
			book.next_serial = free[0] if free else 0
			book.remaining = len(free)


class Cheque(models.Model):
	_name = "veron.cheque"
	_description = "Cheque"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "due_date, id"

	name = fields.Char(compute="_compute_name", store=True)
	direction = fields.Selection([("in", "Received"), ("out", "Issued")], required=True, default="in", readonly=True)
	state = fields.Selection(IN_STATES + OUT_STATES, default="draft", required=True, tracking=True, copy=False)
	partner_id = fields.Many2one("res.partner", required=True, tracking=True)
	amount = fields.Monetary(required=True, tracking=True)
	currency_id = fields.Many2one(related="company_id.currency_id")
	amount_words = fields.Char("Amount in Words", compute="_compute_amount_words")
	sayad_id = fields.Char("Sayad ID", size=16, tracking=True, help="The cheque's 16-digit Sayad id")
	serial = fields.Char("Serial", required=True, tracking=True)
	bank_id = fields.Many2one("res.bank", "Bank")
	branch = fields.Char()
	account_number = fields.Char("Account Number")
	drawer = fields.Char("Drawer", help="Who signed the cheque, when not the customer")
	issue_date = fields.Date(default=fields.Date.context_today)
	due_date = fields.Date(required=True, tracking=True)
	book_id = fields.Many2one("veron.cheque.book", "Cheque Book")
	bank_journal_id = fields.Many2one("account.journal", "Bank Account", domain="[('type', '=', 'bank')]", tracking=True)
	endorse_partner_id = fields.Many2one("res.partner", "Endorsed To", tracking=True)
	move_ids = fields.One2many("account.move", "veron_cheque_id", "Entries", readonly=True)
	move_count = fields.Integer(compute="_compute_move_count")
	note = fields.Text()
	reminded = fields.Boolean(copy=False)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

	_unique_sayad = models.Constraint("unique(sayad_id, direction, company_id)", "A cheque with this Sayad id is already recorded.")

	@api.depends("serial", "partner_id.name", "direction")
	def _compute_name(self):
		for cheque in self:
			cheque.name = _("Cheque %(serial)s - %(partner)s", serial=cheque.serial or "", partner=cheque.partner_id.name or "")

	@api.depends("amount")
	def _compute_amount_words(self):
		for cheque in self:
			cheque.amount_words = cheque.currency_id.with_context(lang=self.env.lang).amount_to_text(cheque.amount) if cheque.amount else ""

	def _compute_move_count(self):
		for cheque in self:
			cheque.move_count = len(cheque.move_ids)

	@api.constrains("sayad_id")
	def _check_sayad(self):
		for cheque in self:
			if cheque.sayad_id and not re.fullmatch(r"\d{16}", cheque.sayad_id):
				raise ValidationError(_("The Sayad id has 16 digits."))

	@api.constrains("amount")
	def _check_amount(self):
		for cheque in self:
			if cheque.amount <= 0:
				raise ValidationError(_("The amount of a cheque is more than zero."))

	@api.onchange("book_id")
	def _onchange_book(self):
		if self.book_id:
			self.bank_journal_id = self.book_id.journal_id
			if self.book_id.next_serial and not self.serial:
				self.serial = str(self.book_id.next_serial)

	# --- accounts

	def _account(self, field):
		account = self.company_id[field]
		if not account:
			label = self.company_id._fields[field].string
			raise UserError(_("Set the account «%s» in Accounting settings, Cheques.", label))
		return account

	def _journal(self):
		if not self.company_id.veron_cheque_journal_id:
			self.company_id._veron_cheque_setup()
		return self.company_id.veron_cheque_journal_id

	def _bank_account(self):
		if not self.bank_journal_id:
			raise UserError(_("Choose the bank account first."))
		return self.bank_journal_id.default_account_id

	def _post(self, label, debit, credit, debit_partner=None, credit_partner=None):
		"""An entry of the cheque's amount from the credit account to the debit account, posted; then
		the cheque's lines on each reconcilable account matched when they balance"""
		self.ensure_one()
		partner = self.partner_id
		move = self.env["account.move"].create({
			"move_type": "entry",
			"journal_id": self._journal().id,
			"date": fields.Date.context_today(self),
			"ref": f"{self.name} - {label}",
			"veron_cheque_id": self.id,
			"line_ids": [
				(0, 0, {"account_id": debit.id, "partner_id": (debit_partner or partner).id, "debit": self.amount, "name": label}),
				(0, 0, {"account_id": credit.id, "partner_id": (credit_partner or partner).id, "credit": self.amount, "name": label}),
			],
		})
		move.action_post()
		lines = self.move_ids.line_ids.filtered(lambda l: l.account_id.reconcile and not l.reconciled)
		for (account, line_partner), group in lines.grouped(lambda l: (l.account_id, l.partner_id)).items():
			if len(group) > 1 and self.currency_id.is_zero(sum(group.mapped("balance"))):
				group.reconcile()
		return move

	def _need(self, *states):
		for cheque in self:
			if cheque.state not in states:
				raise UserError(_("%(cheque)s is %(state)s.", cheque=cheque.name, state=dict(IN_STATES + OUT_STATES)[cheque.state]))

	# --- received cheques

	def action_receive(self):
		self._need("draft")
		for cheque in self.filtered(lambda c: c.direction == "in"):
			cheque._post(_("Cheque received"), cheque._account("veron_cheque_hand_account_id"),
				cheque.partner_id.property_account_receivable_id)
			cheque.state = "hand"
		return True

	def action_deposit(self):
		self._need("hand")
		for cheque in self:
			cheque._bank_account()
			cheque._post(_("Deposited to %s", cheque.bank_journal_id.name), cheque._account("veron_cheque_collection_account_id"),
				cheque._account("veron_cheque_hand_account_id"))
			cheque.state = "collection"
		return True

	def action_cash(self):
		for cheque in self:
			if cheque.direction == "in":
				cheque._need("collection", "hand")
				source = cheque._account("veron_cheque_collection_account_id" if cheque.state == "collection" else "veron_cheque_hand_account_id")
				cheque._post(_("Cheque cashed"), cheque._bank_account(), source)
			else:
				cheque._need("issued")
				cheque._post(_("Cheque cashed"), cheque._account("veron_cheque_payable_account_id"), cheque._bank_account())
			cheque.state = "cashed"
		return True

	def action_bounce(self):
		self._need("collection")
		for cheque in self:
			cheque._post(_("Cheque bounced"), cheque._account("veron_cheque_bounced_account_id"),
				cheque._account("veron_cheque_collection_account_id"))
			cheque.state = "bounced"
			cheque.message_post(body=_("The cheque bounced."))
		return True

	def action_return(self):
		self._need("hand", "bounced")
		for cheque in self:
			source = cheque._account("veron_cheque_hand_account_id" if cheque.state == "hand" else "veron_cheque_bounced_account_id")
			cheque._post(_("Cheque returned to the customer"), cheque.partner_id.property_account_receivable_id, source)
			cheque.state = "returned"
		return True

	def action_endorse(self):
		self._need("hand")
		for cheque in self:
			if not cheque.endorse_partner_id:
				raise UserError(_("Choose who the cheque is endorsed to."))
			vendor = cheque.endorse_partner_id
			cheque._post(_("Cheque endorsed to %s", vendor.name), vendor.property_account_payable_id,
				cheque._account("veron_cheque_hand_account_id"), debit_partner=vendor)
			cheque.state = "endorsed"
		return True

	# --- issued cheques

	def action_issue(self):
		self._need("draft")
		for cheque in self.filtered(lambda c: c.direction == "out"):
			cheque._bank_account()
			cheque._post(_("Cheque issued"), cheque.partner_id.property_account_payable_id,
				cheque._account("veron_cheque_payable_account_id"))
			cheque.state = "issued"
		return True

	def action_cancel(self):
		self._need("issued")
		for cheque in self:
			cheque._post(_("Cheque cancelled"), cheque._account("veron_cheque_payable_account_id"),
				cheque.partner_id.property_account_payable_id)
			cheque.state = "cancelled"
		return True

	def unlink(self):
		if self.filtered(lambda c: c.state != "draft"):
			raise UserError(_("Only a draft cheque is deleted; the others have entries."))
		return super().unlink()

	def action_open_moves(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"name": _("Entries"),
			"res_model": "account.move",
			"view_mode": "list,form",
			"domain": [("veron_cheque_id", "=", self.id)],
		}

	@api.model
	def _cron_remind(self):
		"""A to-do for the cheques due within three days, once each"""
		soon = fields.Date.context_today(self) + timedelta(days=3)
		cheques = self.search([("state", "in", ("hand", "collection", "issued")), ("due_date", "<=", soon), ("reminded", "=", False)])
		for cheque in cheques:
			cheque.activity_schedule("mail.mail_activity_data_todo", date_deadline=cheque.due_date,
				summary=_("Cheque due: %s", cheque.name), user_id=(cheque.create_uid or self.env.user).id)
		cheques.write({"reminded": True})


class AccountMove(models.Model):
	_inherit = "account.move"

	veron_cheque_id = fields.Many2one("veron.cheque", "Cheque", index="btree_not_null", readonly=True, copy=False)
