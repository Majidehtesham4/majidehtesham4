"""The record of a company brought from an older Odoo: what came, what did not, the comparison of its balances
with the old system, and the steps a person confirms here: posting the entries, redoing the reconciliations and
applying the stock counted"""

import json
import logging
import time
from contextlib import contextmanager

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools.translate import LazyTranslate
from odoo.exceptions import UserError

from ..services.importer import MODULE

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

STEP_SECONDS = 50
# What the importer counts, by the names it gives
LABELS = {
	"contacts": _lt("Contacts"), "bank accounts": _lt("Bank Accounts"), "products": _lt("Products"),
	"vendor prices": _lt("Vendor Prices"), "employees": _lt("Employees"), "users (archived)": _lt("Users (archived)"),
	"journal entries": _lt("Journal Entries and Invoices"), "payments": _lt("Payments"),
	"bank statements": _lt("Bank Statements"), "bank statement lines": _lt("Bank Statement Lines"),
	"reconciliations to redo": _lt("Reconciliations to Redo"), "sale orders": _lt("Sale Orders"),
	"sale order lines": _lt("Sale Order Lines"), "purchase orders": _lt("Purchase Orders"),
	"purchase order lines": _lt("Purchase Order Lines"), "receipts and deliveries": _lt("Receipts and Deliveries"),
	"transfer lines": _lt("Transfer Lines"), "stock locations": _lt("Stock Locations"),
	"lots and serial numbers": _lt("Lots and Serial Numbers"), "stock counted": _lt("Stock Counted"),
	"pictures": _lt("Pictures"), "attached files": _lt("Attached Files"), "notes and messages": _lt("Notes and Messages"),
	"custom fields": _lt("Fields Added by Hand or Studio"), "exchange rates": _lt("Exchange Rates"),
	"manufacturing orders": _lt("Manufacturing Orders"), "work orders": _lt("Work Orders"),
	"work times": _lt("Work Times"), "product documents": _lt("Product Documents"),
}
SEQUENCE_PARAM = "sequence.mixin.constraint_start_date"


class VeronMigration(models.Model):
	_name = "veron.migration"
	_description = "Company Brought From Odoo"
	_order = "id desc"

	name = fields.Char(required=True, readonly=True)
	company_id = fields.Many2one("res.company", required=True, readonly=True, default=lambda self: self.env.company)
	source_db = fields.Char("Old Database", readonly=True,
		help="The backup loaded on this server, read only; delete it in the database manager once all is confirmed")
	source_version = fields.Char("Old Version", readonly=True)
	source_company = fields.Integer("Company in the Backup", readonly=True)
	state = fields.Selection([("imported", "Brought, to Confirm"), ("confirming", "Confirming"), ("done", "Confirmed")],
		default="imported", required=True, readonly=True)
	counts_json = fields.Text(readonly=True)
	notes = fields.Text("To Check", readonly=True)
	left_json = fields.Text(readonly=True)
	move_states_json = fields.Text(readonly=True)
	groups_json = fields.Text(readonly=True)
	payment_states_json = fields.Text(readonly=True)
	moves_to_post = fields.Integer("Entries to Post", readonly=True)
	moves_posted = fields.Integer("Entries Posted", readonly=True)
	reconciled = fields.Integer("Reconciliations Redone", readonly=True)
	failures = fields.Text("Not Confirmed", readonly=True)
	stock_applied = fields.Boolean(readonly=True)
	has_stock = fields.Boolean(compute="_compute_has_stock")
	summary_html = fields.Html("Brought", compute="_compute_summary_html", sanitize=False)
	comparison_html = fields.Html("Comparison", readonly=True, sanitize=False)

	def _compute_has_stock(self):
		for record in self:
			record.has_stock = "stock.quant" in self.env

	@api.depends("counts_json", "left_json")
	def _compute_summary_html(self):
		for record in self:
			counts = json.loads(record.counts_json or "{}")
			rows = Markup("").join(Markup("<tr><td>%s</td><td class='text-end'>%s</td></tr>") % (
				str(LABELS[name]) if name in LABELS else self.env["ir.model"]._get(name).name or name, f"{count:,}")
				for name, count in counts.items() if count)
			left = json.loads(record.left_json or "[]")
			left_rows = Markup("").join(Markup("<tr><td>%s</td><td>%s</td><td class='text-end'>%s</td></tr>") % (model,
				modules, f"{count:,}") for model, modules, count in left[:80])
			html = Markup("<table class='table table-sm'><thead><tr><th>%s</th><th class='text-end'>%s</th></tr></thead>"
				"<tbody>%s</tbody></table>") % (_("Brought"), _("Records"), rows)
			if left_rows:
				html += Markup("<h5 class='mt-4'>%s</h5><p class='text-muted'>%s</p><table class='table table-sm'><thead>"
					"<tr><th>%s</th><th>%s</th><th class='text-end'>%s</th></tr></thead><tbody>%s</tbody></table>") % (
					_("Not Brought"), _("Data of the old system that has no place in this program: modules of Odoo "
					"Enterprise, the company's own modules, and history kept only in the old system."), _("Kind"),
					_("Module"), _("Records"), left_rows)
			record.summary_html = html

	# --- the old database

	@contextmanager
	def _old_cursor(self):
		from odoo.sql_db import db_connect

		if self.env.context.get("migration_old_cursor"):
			# The tests read the old company from their own transaction
			yield self.env.context["migration_old_cursor"]
			return
		if not self.source_db:
			raise UserError(_("The old database of this migration is not on this server any more."))
		try:
			cr = db_connect(self.source_db).cursor()
		except Exception as error:
			raise UserError(_("The old database %(name)s could not be opened: %(error)s", name=self.source_db,
				error=error)) from error
		try:
			yield cr
		finally:
			cr.close()

	def _mapped(self, model):
		"""{old id: id here} of the records of a model brought by this migration"""
		self.env.cr.execute("SELECT name, res_id FROM ir_model_data WHERE module = %s AND model = %s AND name LIKE %s",
			(MODULE, model, f"%\\_\\_{self.source_company}\\_\\_%"))
		return {int(name.rsplit("__", 1)[1]): res_id for name, res_id in self.env.cr.fetchall()}

	def _move_states(self):
		return {int(key): value for key, value in json.loads(self.move_states_json or "{}").items()}

	def action_compare(self):
		"""The balance of each account in the old system next to its balance here, over the entries that were
		posted there"""
		self.ensure_one()
		accounts = self._mapped("account.account")
		with self._old_cursor() as cr:
			cr.execute("SELECT l.account_id, sum(l.balance) FROM account_move_line l JOIN account_move m ON m.id = l.move_id "
				"WHERE m.state = 'posted' AND l.company_id = %s GROUP BY l.account_id", (self.source_company,))
			old = {}
			for account_id, balance in cr.fetchall():
				here = accounts.get(account_id)
				old[here] = old.get(here, 0.0) + float(balance or 0.0)
			cr.execute("SELECT count(*) FROM account_move WHERE state = 'posted' AND company_id = %s", (self.source_company,))
			old_count = cr.fetchone()[0]
		posted_there = [move for move, state in self._move_states().items() if state == "posted"]
		new = {}
		if posted_there:
			self.env.cr.execute("SELECT account_id, sum(balance) FROM account_move_line WHERE move_id = ANY(%s) GROUP BY "
				"account_id", (posted_there,))
			new = {account: float(balance or 0.0) for account, balance in self.env.cr.fetchall()}
		Account = self.env["account.account"].with_company(self.company_id)
		currency = self.company_id.currency_id
		rows, differences = [], 0
		for account_id in sorted(set(old) | set(new), key=lambda a: Account.browse(a).code or "" if a else "~"):
			there, here = old.get(account_id, 0.0), new.get(account_id, 0.0)
			differ = not currency.is_zero(there - here)
			differences += differ
			account = Account.browse(account_id) if account_id else None
			label = f"{account.code} {account.name}" if account else _("(an account not brought)")
			rows.append(Markup("<tr class='%s'><td>%s</td><td class='text-end'>%s</td><td class='text-end'>%s</td>"
				"<td class='text-end'>%s</td></tr>") % ("table-danger" if differ else "", label, f"{there:,.0f}",
				f"{here:,.0f}", f"{there - here:,.0f}" if differ else ""))
		verdict = _("Every account has the same balance here as in the old system.") if not differences else \
			_("%s accounts differ: see the rows in red.", differences)
		self.comparison_html = Markup("<p><b>%s</b></p><p>%s</p><table class='table table-sm'><thead><tr><th>%s</th>"
			"<th class='text-end'>%s</th><th class='text-end'>%s</th><th class='text-end'>%s</th></tr></thead><tbody>%s"
			"</tbody></table>") % (verdict, _("Posted entries in the old system: %(old)s; brought: %(new)s.",
			old=f"{old_count:,}", new=f"{len(posted_there):,}"), _("Account"), _("Old System"), _("Here"),
			_("Difference"), Markup("").join(rows))
		return True

	# --- the confirmation, by a person

	def _check_manager(self):
		if not self.env.user.has_group("account.group_account_manager"):
			raise UserError(_("Only an accounting manager confirms the entries of a migration."))

	def action_confirm(self):
		"""Posts the entries that were posted in the old system, cancels the cancelled ones and redoes the
		reconciliations, in steps in the background"""
		self.ensure_one()
		self._check_manager()
		if self.state != "imported":
			return True
		self.state = "confirming"
		self.env.ref("veron_migration.cron_confirm")._trigger()
		return True

	@api.model
	def _cron_confirm(self):
		start = time.monotonic()
		for migration in self.search([("state", "=", "confirming")]):
			while time.monotonic() - start < STEP_SECONDS:
				finished = migration._confirm_step(200)
				self.env.cr.commit()
				if finished:
					break
			if migration.state == "confirming":
				self.env.ref("veron_migration.cron_confirm")._trigger()
				return

	@contextmanager
	def _quiet_valuation(self):
		"""Stock valuation as periodic while old documents are posted and the stock applied: their valuation is
		already in the entries brought, and would be counted twice"""
		company = self.company_id
		saved_company = company.inventory_valuation if "inventory_valuation" in company._fields else None
		categories = self.env["product.category"].with_company(company).search([]) \
			if "property_valuation" in self.env["product.category"]._fields else self.env["product.category"]
		saved = {category.id: category.property_valuation for category in categories}
		try:
			if saved_company is not None:
				company.inventory_valuation = "periodic"
			for category in categories:
				if category.property_valuation != "periodic":
					category.property_valuation = "periodic"
			yield
		finally:
			if saved_company is not None:
				company.inventory_valuation = saved_company
			for category in categories:
				if saved.get(category.id) and category.property_valuation != saved[category.id]:
					category.property_valuation = saved[category.id]

	@contextmanager
	def _old_numbers(self, moves):
		"""The numbers of the old entries kept as they are while they are posted: a number made by the old system
		need not follow the pattern of the journals here"""
		Param = self.env["ir.config_parameter"].sudo()
		saved = Param.get_param(SEQUENCE_PARAM)
		last = max(moves.mapped("date"))
		Param.set_param(SEQUENCE_PARAM, fields.Date.to_string(last))
		try:
			yield
		finally:
			Param.set_param(SEQUENCE_PARAM, saved or "1970-01-01")

	def _fail(self, message):
		self.failures = ((self.failures or "") + message + "\n")[-20000:]

	def _confirm_step(self, limit):
		"""One part of the confirmation; True when all is done"""
		self.ensure_one()
		states = self._move_states()
		Move = self.env["account.move"].with_company(self.company_id).with_context(skip_invoice_sync=True,
			no_exchange_difference=True, mail_notrack=True, tracking_disable=True)
		to_post = Move.browse([move for move, state in states.items() if state == "posted"]).exists()
		drafts = to_post.filtered(lambda m: m.state == "draft").sorted(lambda m: (m.date, m.id))[:limit]
		if drafts:
			with self._quiet_valuation(), self._old_numbers(drafts):
				try:
					with self.env.cr.savepoint():
						drafts._post(soft=False)
				except Exception:  # noqa: BLE001 - one by one, to find the entries that cannot be posted
					for move in drafts:
						try:
							with self.env.cr.savepoint():
								move._post(soft=False)
						except Exception as error:  # noqa: BLE001 - shown on the migration, the others go on
							self._fail(_("Entry %(name)s of %(date)s was not posted: %(error)s", name=move.name,
								date=move.date, error=str(error).splitlines()[0][:300]))
							# Left as a draft and not tried again
							states[move.id] = "draft_failed"
			self.write({"moves_posted": len(to_post.filtered(lambda m: m.state == "posted")),
				"move_states_json": json.dumps(states)})
			return False
		cancelled = Move.browse([move for move, state in states.items() if state == "cancel"]).exists().filtered(
			lambda m: m.state == "draft")
		if cancelled:
			cancelled.button_cancel()
			return False
		groups = json.loads(self.groups_json or "[]")
		if self.reconciled < len(groups):
			Line = self.env["account.move.line"].with_context(no_exchange_difference=True)
			done = self.reconciled
			for group in groups[done:done + limit]:
				lines = Line.browse(group).exists().filtered(lambda l: l.parent_state == "posted" and not l.reconciled)
				if len(lines) > 1:
					try:
						with self.env.cr.savepoint():
							lines.reconcile()
					except Exception as error:  # noqa: BLE001
						self._fail(_("Lines %(lines)s were not reconciled: %(error)s", lines=", ".join(
							lines.mapped("move_name")), error=str(error).splitlines()[0][:300]))
				done += 1
			self.reconciled = done
			return False
		# The payments as they were: in process, paid (worked out again from their reconciliation) or cancelled
		payment_states = {int(key): value for key, value in json.loads(self.payment_states_json or "{}").items()}
		Payment = self.env["account.payment"]
		valued = Payment.browse([p for p, state in payment_states.items() if state in ("posted", "in_process", "paid")])
		valued = valued.exists().filtered(lambda p: p.state == "draft" and p.move_id.state == "posted")
		if valued:
			valued.write({"state": "in_process"})
			valued._compute_state()
		cancelled = Payment.browse([p for p, state in payment_states.items() if state in ("cancel", "canceled")]).exists()
		cancelled.filtered(lambda p: p.state == "draft").write({"state": "canceled"})
		self.state = "done"
		self.action_compare()
		return True

	def action_apply_stock(self):
		"""The quantities counted in the migration become the stock on hand, without new accounting entries"""
		self.ensure_one()
		group = self.env.ref("stock.group_stock_manager", raise_if_not_found=False)
		if not group or group not in self.env.user.all_group_ids:
			raise UserError(_("Only an inventory manager applies the stock of a migration."))
		quants = self.env["stock.quant"].search([("inventory_quantity_set", "=", True),
			("company_id", "=", self.company_id.id)])
		if quants:
			with self._quiet_valuation():
				quants.with_context(inventory_name=_("Stock brought from %s", self.name)).action_apply_inventory()
		self.stock_applied = True
		return True

	def action_open_users(self):
		"""The users brought, archived: each is checked, given access and invited by an administrator"""
		users = list(self._mapped("res.users").values())
		return {"type": "ir.actions.act_window", "name": _("Users Brought"), "res_model": "res.users",
			"view_mode": "list,form", "domain": [("id", "in", users)], "context": {"active_test": False}}

	def action_open_moves(self):
		moves = list(self._move_states())
		return {"type": "ir.actions.act_window", "name": _("Entries Brought"), "res_model": "account.move",
			"view_mode": "list,form", "domain": [("id", "in", moves)], "context": {"create": False}}

	@api.model
	def _record(self, work, version, source_db):
		"""The record of a run of the importer"""
		migration = self.search([("source_db", "=", source_db), ("company_id", "=", work.company.id)], limit=1)
		states = {}
		if migration:
			states = migration._move_states()
		for old_id, state in work.move_states.items():
			new = work.map["account.move"].get(old_id)
			if new and new not in states:
				states[new] = state
		values = {"name": _("%(company)s from Odoo %(version)s", company=work.old_company["name"], version=version),
			"company_id": work.company.id, "source_db": source_db, "source_version": version,
			"source_company": work.cid, "counts_json": json.dumps(dict(work.counts)),
			"notes": "\n".join(work.notes) or False, "left_json": json.dumps(work.left_out()),
			"move_states_json": json.dumps(states), "groups_json": json.dumps(work.groups),
			"payment_states_json": json.dumps({**json.loads(migration.payment_states_json or "{}"), **{str(k): v for k, v in
				work.payment_states.items()}}),
			"moves_to_post": sum(1 for state in states.values() if state == "posted")}
		if migration:
			# Brought again: what is new waits for a new confirmation; the reconciliations are looked at anew
			values.update({"state": "imported", "reconciled": 0})
		if migration:
			migration.write(values)
		else:
			migration = self.create(values)
		return migration
