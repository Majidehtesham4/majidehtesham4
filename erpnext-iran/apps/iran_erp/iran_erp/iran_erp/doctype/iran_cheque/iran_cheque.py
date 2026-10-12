# Copyright (c) 2026, Majid Ehtesham and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from iran_erp.utils.national_id import normalize_digits

# Account numbers in the Iranian chart, used when Iran ERP Settings names no account for the company
DEFAULT_ACCOUNT_NUMBERS = {
	"cheques_receivable_account": "1302",
	"cheques_in_collection_account": "1303",
	"cheques_payable_account": "3102",
}

# action: (cheque type, statuses it starts from, status it ends in)
ACTIONS = {
	"deposit": ("Received", ("In Hand",), "Deposited"),
	"clear": (None, ("In Hand", "Deposited", "Issued"), "Cleared"),
	"bounce": (None, ("In Hand", "Deposited", "Issued"), "Bounced"),
	"return": (None, ("In Hand", "Issued"), "Returned"),
	"endorse": ("Received", ("In Hand",), "Endorsed"),
}


class IranCheque(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be more than zero"))
		if self.sayad_id:
			self.sayad_id = normalize_digits(self.sayad_id).strip()
			if not re.fullmatch(r"\d{16}", self.sayad_id):
				frappe.throw(_("Sayad ID must be 16 digits"))
		self.cheque_number = normalize_digits(self.cheque_number or "").strip()
		if self.cheque_type == "Issued" and not self.bank_account:
			frappe.throw(_("Set the bank account the cheque is drawn on"))
		if self.bank_account:
			validate_account(self.bank_account, self.company, ("Bank", "Cash"))
		if self.against_invoice:
			self.validate_against_invoice()
		self.party_name = get_party_name(self.party_type, self.party)
		if self.docstatus == 0:
			self.status = "Draft"

	def validate_against_invoice(self):
		expected = "Sales Invoice" if self.cheque_type == "Received" else "Purchase Invoice"
		if self.against_doctype != expected:
			frappe.throw(_("A {0} cheque can only be against a {1}").format(_(self.cheque_type), _(expected)))
		invoice = frappe.db.get_value(
			expected,
			self.against_invoice,
			["docstatus", "company", "customer" if expected == "Sales Invoice" else "supplier"],
			as_dict=True,
		)
		party = invoice and (invoice.get("customer") or invoice.get("supplier"))
		if not invoice or invoice.docstatus != 1 or invoice.company != self.company or party != self.party:
			frappe.throw(_("{0} is not a submitted invoice of this party").format(self.against_invoice))

	def on_submit(self):
		if self.cheque_type == "Received":
			self.cheque_account = get_cheque_account(self.company, "cheques_receivable_account")
			entry = self.make_entry(
				self.posting_date,
				debit=self.row(self.cheque_account),
				credit=self.party_row(self.party_type, self.party, payment=True),
				action=_("Receive Cheque"),
			)
			status = "In Hand"
		else:
			self.cheque_account = get_cheque_account(self.company, "cheques_payable_account")
			entry = self.make_entry(
				self.posting_date,
				debit=self.party_row(self.party_type, self.party, payment=True),
				credit=self.row(self.cheque_account),
				action=_("Issue Cheque"),
			)
			status = "Issued"
		self.db_set("cheque_account", self.cheque_account)
		self.log(
			self.posting_date,
			_("Receive Cheque") if self.cheque_type == "Received" else _("Issue Cheque"),
			status,
			entry,
		)

	def on_cancel(self):
		# Undo every entry, newest first
		for row in reversed(self.history):
			if (
				row.journal_entry
				and frappe.db.get_value("Journal Entry", row.journal_entry, "docstatus") == 1
			):
				frappe.get_doc("Journal Entry", row.journal_entry).cancel()
		self.db_set("status", "Cancelled")

	@frappe.whitelist()
	def take_action(
		self,
		action: str,
		date: str | None = None,
		bank_account: str | None = None,
		endorsed_to_type: str | None = None,
		endorsed_to: str | None = None,
		remarks: str | None = None,
	):
		self.check_permission("submit")
		if self.docstatus != 1:
			frappe.throw(_("Submit the cheque first"))
		if action not in ACTIONS:
			frappe.throw(_("Unknown action {0}").format(action))
		cheque_type, from_statuses, to_status = ACTIONS[action]
		if (cheque_type and cheque_type != self.cheque_type) or self.status not in from_statuses:
			frappe.throw(_("A cheque in status {0} cannot be {1}").format(_(self.status), _(to_status)))

		date = date or nowdate()
		if getdate(date) < getdate(self.posting_date):
			frappe.throw(_("The date cannot be before the posting date of the cheque"))
		if bank_account:
			validate_account(bank_account, self.company, ("Bank", "Cash"))
			self.db_set("bank_account", bank_account)

		entry = getattr(self, f"_{action}")(date, endorsed_to_type, endorsed_to)
		self.log(date, action_labels()[action], to_status, entry, remarks)
		return self.status

	def _deposit(self, date, *args):
		self.require_bank_account()
		return self.make_entry(
			date,
			debit=self.row(get_cheque_account(self.company, "cheques_in_collection_account")),
			credit=self.row(self.cheque_account),
			action=_("Deposit to Bank"),
		)

	def _clear(self, date, *args):
		self.require_bank_account()
		if self.cheque_type == "Issued":
			return self.make_entry(
				date,
				debit=self.row(self.cheque_account),
				credit=self.row(self.bank_account),
				action=_("Mark as Cleared"),
			)
		return self.make_entry(
			date,
			debit=self.row(self.bank_account),
			credit=self.row(self.holding_account()),
			action=_("Mark as Cleared"),
		)

	def _bounce(self, date, *args):
		# The party owes (or is owed) the amount again
		if self.cheque_type == "Issued":
			return self.make_entry(
				date,
				debit=self.row(self.cheque_account),
				credit=self.party_row(self.party_type, self.party),
				action=_("Mark as Bounced"),
			)
		return self.make_entry(
			date,
			debit=self.party_row(self.party_type, self.party),
			credit=self.row(self.holding_account()),
			action=_("Mark as Bounced"),
		)

	def _return(self, date, *args):
		return self._bounce(date)

	def _endorse(self, date, endorsed_to_type, endorsed_to):
		if not (endorsed_to_type and endorsed_to):
			frappe.throw(_("Choose who the cheque is endorsed to"))
		self.db_set({"endorsed_to_type": endorsed_to_type, "endorsed_to": endorsed_to})
		return self.make_entry(
			date,
			debit=self.party_row(endorsed_to_type, endorsed_to, payment=True),
			credit=self.row(self.cheque_account),
			action=_("Endorse to Third Party"),
		)

	def holding_account(self):
		"""Where a received cheque sits now: with the company, or with the bank for collection."""
		if self.status == "Deposited":
			return get_cheque_account(self.company, "cheques_in_collection_account")
		return self.cheque_account

	def require_bank_account(self):
		if not self.bank_account:
			frappe.throw(_("Set the bank account first"))

	def row(self, account):
		return {"account": account}

	def party_row(self, party_type, party, payment=False):
		"""A payment row settles the invoice the cheque is against, or else stays open as an advance."""
		from erpnext.accounts.party import get_party_account

		row = {
			"account": get_party_account(party_type, party, self.company),
			"party_type": party_type,
			"party": party,
		}
		if payment and self.against_invoice and party == self.party:
			row.update({"reference_type": self.against_doctype, "reference_name": self.against_invoice})
		elif payment:
			row["is_advance"] = "Yes"
		return row

	def make_entry(self, posting_date, debit, credit, action):
		amount = flt(self.amount)
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": self.company,
				"posting_date": posting_date,
				"cheque_no": self.cheque_number,
				"cheque_date": self.due_date,
				"user_remark": _("{0} cheque {1} ({2}): {3}").format(
					_(self.cheque_type), self.cheque_number, self.name, action
				),
				"accounts": [
					{**debit, "debit_in_account_currency": amount},
					{**credit, "credit_in_account_currency": amount},
				],
			}
		)
		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()
		return entry.name

	def log(self, date, action, to_status, journal_entry, remarks=None):
		from_status = self.status
		self.append(
			"history",
			{
				"date": date,
				"action": action,
				"from_status": from_status,
				"to_status": to_status,
				"journal_entry": journal_entry,
				"remarks": remarks,
			},
		)
		row = self.history[-1]
		row.db_insert()
		self.status = to_status
		self.db_set("status", to_status)


def action_labels():
	return {
		"deposit": _("Deposit to Bank"),
		"clear": _("Mark as Cleared"),
		"bounce": _("Mark as Bounced"),
		"return": _("Return to Party"),
		"endorse": _("Endorse to Third Party"),
	}


def get_party_name(party_type, party):
	if not (party_type and party):
		return None
	field = {"Customer": "customer_name", "Supplier": "supplier_name", "Employee": "employee_name"}.get(
		party_type, "title"
	)
	return frappe.db.get_value(party_type, party, field) or party


def get_cheque_account(company: str, fieldname: str) -> str:
	account = frappe.db.get_value(
		"Iran Cheque Account", {"parent": "Iran ERP Settings", "company": company}, fieldname
	) or frappe.db.get_value(
		"Account", {"company": company, "account_number": DEFAULT_ACCOUNT_NUMBERS[fieldname], "is_group": 0}
	)
	if not account:
		label = frappe.get_meta("Iran Cheque Account").get_label(fieldname)
		frappe.throw(
			_("Set the {0} account for {1} in Iran ERP Settings").format(_(label), company),
			title=_("Missing Account"),
		)
	return account


def validate_account(account, company, account_types):
	details = frappe.db.get_value("Account", account, ["company", "account_type", "is_group"], as_dict=True)
	if (
		not details
		or details.company != company
		or details.is_group
		or details.account_type not in account_types
	):
		frappe.throw(_("{0} is not a bank or cash account of {1}").format(account, company))
