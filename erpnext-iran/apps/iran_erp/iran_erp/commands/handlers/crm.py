import frappe
from frappe import _

from iran_erp.commands import entities
from iran_erp.commands.handlers import company, doc_link, document_list, period_or, require


def create_lead(context):
	require("Lead", "create")
	name = context.get("name")
	doc = frappe.get_doc(
		{"doctype": "Lead", "lead_name": name, "mobile_no": context.get("mobile"), "company": company()}
	).insert()
	entities.forget("lead")
	return {"answer": _("Lead {0} was created.").format(name), "actions": [doc_link("Lead", doc.name)]}


def leads(context):
	start, end, label = period_or(context)
	filters = {"creation": ["between", [start, f"{end} 23:59:59"]]}
	if not context.get("period"):
		filters = {"status": ["in", ["Lead", "Open", "Replied", "Interested"]]}
		label = _("open")
	return document_list(
		"Lead",
		filters,
		[
			("name", _("Lead"), "link"),
			("lead_name", _("Name"), ""),
			("mobile_no", _("Mobile"), ""),
			("status", _("Status"), "status"),
		],
		_("Leads") + f" ({label})",
		empty=_("No leads."),
	)


def opportunities(context):
	return document_list(
		"Opportunity",
		{"status": ["in", ["Open", "Replied"]], "company": company()},
		[
			("name", _("Opportunity"), "link"),
			("customer_name", _("Customer"), ""),
			("expected_closing", _("Expected Closing"), "date"),
			("opportunity_amount", _("Amount"), "money"),
		],
		_("Open opportunities"),
		order_by="expected_closing asc",
		empty=_("No open opportunities."),
	)
