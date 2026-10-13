from urllib.parse import quote

import frappe
from frappe import _

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands.catalog import DOCTYPES, REPORTS
from iran_erp.commands.engine import NeedConfirm, NeedSlot
from iran_erp.commands.handlers import link, list_url, money, report_url, require


def _name(table, key, plural=False):
	names = table.get(key, [key])
	return names[1] if plural and len(names) > 1 else names[0]


def _open(text, url):
	# "open": the chat takes the user there straight away; the link stays for going back to it
	return {"answer": text, "actions": [{**link(_("Open"), url), "open": True}]}


def open_list(context):
	doctype = context.get("doctype")
	require(doctype)
	if frappe.get_meta(doctype).issingle:
		return _open(_("Opening {0}.").format(_(doctype)), get_url_to_form(doctype, doctype))
	return _open(
		_("Opening the list of {0}.").format(_name(DOCTYPES, doctype, plural=True)), list_url(doctype)
	)


def new_document(context):
	doctype = context.get("doctype")
	require(doctype, "create")
	path = list_url(doctype) + "/new"
	return _open(_("Opening a new {0} form.").format(_name(DOCTYPES, doctype)), path)


def open_report(context):
	report = context.get("report")
	if not frappe.has_permission("Report", "read", report) and not frappe.db.exists("Report", report):
		raise frappe.PermissionError
	return _open(_("Opening the report {0}.").format(_name(REPORTS, report)), report_url(report))


def _document(context):
	doctype, _sep, name = (context.get("document") or "").partition(":")
	if not name:
		raise NeedSlot("document", _("Which document? Write its number."))
	if not frappe.has_permission(doctype, "read", name):
		raise frappe.PermissionError
	return doctype, name


def open_document(context):
	doctype, name = _document(context)
	return _open(_("Opening {0} {1}.").format(_(doctype), name), get_url_to_form(doctype, name))


def print_document(context):
	if context.get("document"):
		doctype, name = _document(context)
	else:
		doctype = "Sales Invoice"
		names = frappe.get_list(
			doctype, filters={"owner": frappe.session.user}, pluck="name", order_by="creation desc", limit=1
		)
		if not names:
			raise NeedSlot("document", _("Which document? Write its number."))
		name = names[0]
	url = f"/desk/print/{quote(doctype)}/{quote(name)}"
	return _open(_("Opening the print view of {0} {1}.").format(_(doctype), name), url)


def search(context):
	text = context.get("text")
	lines = []
	actions = []
	for doctype, field in (
		("Customer", "customer_name"),
		("Supplier", "supplier_name"),
		("Item", "item_name"),
		("Lead", "lead_name"),
	):
		if not frappe.has_permission(doctype, "read"):
			continue
		like = "%" + "%".join(text.split()) + "%"
		rows = frappe.get_list(
			doctype,
			or_filters={field: ["like", like], "name": ["like", like]},
			fields=["name", field],
			limit=5,
		)
		for row in rows:
			lines.append(
				f"- {_(doctype)}: [{row.get(field) or row.name}]({get_url_to_form(doctype, row.name)})"
			)
	if not lines:
		return _("Nothing matched «{0}».").format(text)
	return {"answer": _("Results for «{0}»:").format(text) + "\n" + "\n".join(lines), "actions": actions}


def submit_document(context):
	doctype, name = _document(context)
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 0:
		return _("{0} {1} is not a draft, so there is nothing to submit.").format(_(doctype), name)
	if not frappe.has_permission(doctype, "submit", doc):
		raise frappe.PermissionError
	if not context.confirmed:
		total = (
			doc.get("grand_total") or doc.get("total_debit") or doc.get("paid_amount") or doc.get("amount")
		)
		summary = _("Submit {0} {1}").format(_(doctype), name)
		party = doc.get("customer_name") or doc.get("supplier_name") or doc.get("party_name")
		if party:
			summary += f" — {party}"
		if total:
			summary += f" — {money(total)}"
		raise NeedConfirm(summary + ". " + _("A submitted document can only be cancelled, not edited."))
	doc.submit()
	return {
		"answer": _("{0} {1} was submitted.").format(_(doctype), name),
		"actions": [{"updated": doctype, "name": name, "url": get_url_to_form(doctype, name)}],
	}
