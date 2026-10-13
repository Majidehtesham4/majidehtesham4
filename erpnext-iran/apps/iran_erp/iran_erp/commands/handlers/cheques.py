import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands.handlers import (
	company,
	doc_link,
	document_list,
	jdate,
	link,
	money,
	party_label,
	require,
)


def columns():
	return [
		("name", _("Cheque"), "link"),
		("party_name", _("Party"), ""),
		("cheque_number", _("Number"), ""),
		("due_date", _("Due Date"), "date"),
		("amount", _("Amount"), "money"),
		("status", _("Status"), "status"),
	]


def _with_total(result, filters):
	rows = frappe.get_list(
		"Iran Cheque",
		filters=filters,
		fields=["cheque_type", {"SUM": "amount", "as": "total"}],
		group_by="cheque_type",
	)
	parts = [
		(_("received") if r.cheque_type == "Received" else _("issued")) + f": {money(r.total)}"
		for r in rows
		if r.total
	]
	if parts:
		result["answer"] += "\n\n" + _("Total") + " — " + "، ".join(parts)
	return result


def cheques_due(context):
	period = context.get("period")
	start, end = (period["from"], period["to"]) if period else (nowdate(), add_days(nowdate(), 7))
	label = period["label"] if period else _("the next 7 days")
	filters = {
		"docstatus": 1,
		"company": company(),
		"status": ["in", ["In Hand", "Deposited", "Issued"]],
		"due_date": ["between", [start, end]],
	}
	result = document_list(
		"Iran Cheque",
		filters,
		columns(),
		_("Cheques due in {0}").format(label),
		order_by="due_date asc",
		empty=_("No cheques fall due in {0}.").format(label),
	)
	return _with_total(result, filters)


def cheques_received(context):
	filters = {
		"docstatus": 1,
		"company": company(),
		"cheque_type": "Received",
		"status": ["in", ["In Hand", "Deposited"]],
	}
	if context.get("customer"):
		filters.update(party_type="Customer", party=context.get("customer"))
	result = document_list(
		"Iran Cheque",
		filters,
		columns(),
		_("Received cheques not yet cleared"),
		order_by="due_date asc",
		empty=_("No received cheques are pending."),
	)
	return _with_total(result, filters)


def cheques_issued(context):
	filters = {"docstatus": 1, "company": company(), "cheque_type": "Issued", "status": "Issued"}
	if context.get("supplier"):
		filters.update(party_type="Supplier", party=context.get("supplier"))
	result = document_list(
		"Iran Cheque",
		filters,
		columns(),
		_("Issued cheques not yet cleared"),
		order_by="due_date asc",
		empty=_("No issued cheques are pending."),
	)
	return _with_total(result, filters)


def bounced_cheques(context):
	filters = {"docstatus": 1, "company": company(), "status": "Bounced"}
	result = document_list(
		"Iran Cheque",
		filters,
		columns(),
		_("Bounced cheques"),
		order_by="due_date desc",
		empty=_("No bounced cheques."),
	)
	return _with_total(result, filters)


def _register(context, cheque_type, party_type, party):
	require("Iran Cheque", "create")
	number = str(context.get("number") or "")
	the_company = company()
	doc = frappe.get_doc(
		{
			"doctype": "Iran Cheque",
			"cheque_type": cheque_type,
			"company": the_company,
			"party_type": party_type,
			"party": party,
			"cheque_number": number[-8:] if len(number) == 16 else number,
			"sayad_id": number if len(number) == 16 else None,
			"amount": flt(context.get("amount")),
			"posting_date": nowdate(),
			"due_date": context.get("date"),
		}
	)
	if cheque_type == "Issued":
		bank = context.get("bank")
		doc.bank_account = (
			(frappe.db.get_value("Bank Account", bank, "account") if bank else None)
			or frappe.get_cached_value("Company", the_company, "default_bank_account")
		) or frappe.db.get_value(
			"Account", {"company": the_company, "account_type": "Bank", "is_group": 0, "disabled": 0}
		)
	doc.insert()
	kind = _("Received cheque") if cheque_type == "Received" else _("Issued cheque")
	return {
		"answer": _("Draft {0}: {1}, {2}, due {3}. Submit it to record it.").format(
			kind, party_label(party_type, party), money(doc.amount), jdate(doc.due_date)
		),
		"actions": [doc_link("Iran Cheque", doc.name)],
	}


def register_received(context):
	return _register(context, "Received", "Customer", context.get("customer"))


def register_issued(context):
	return _register(context, "Issued", "Supplier", context.get("supplier"))


def cheque_info(context):
	require("Iran Cheque")
	number = str(context.get("number"))
	rows = frappe.get_list(
		"Iran Cheque",
		or_filters={"cheque_number": number, "sayad_id": number, "name": ["like", f"%{number}"]},
		fields=["name", "cheque_type", "party_name", "amount", "due_date", "status"],
		limit=5,
	)
	if not rows:
		return _("No cheque with number {0} was found.").format(number)
	lines = [
		f"- [{r.name}]({get_url_to_form('Iran Cheque', r.name)}): {_(r.cheque_type)}، {r.party_name}، {money(r.amount)}، {_('Due Date')} {jdate(r.due_date)} — **{_(r.status)}**"
		for r in rows
	]
	return "\n".join(lines)
