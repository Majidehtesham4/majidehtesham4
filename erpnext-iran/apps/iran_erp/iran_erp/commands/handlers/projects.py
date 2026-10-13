import frappe
from frappe import _
from frappe.utils import nowdate

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands.handlers import company, doc_link, document_list, jdate, link, number, require


def create_todo(context):
	require("ToDo", "create")
	text = context.get("text")
	date = context.get("date")
	doc = frappe.get_doc(
		{"doctype": "ToDo", "description": text, "date": date, "allocated_to": frappe.session.user}
	).insert()
	answer = _("Noted: {0}").format(text)
	if date:
		answer += " — " + jdate(date)
	return {"answer": answer, "actions": [doc_link("ToDo", doc.name)]}


def my_todos(context):
	return document_list(
		"ToDo",
		{"allocated_to": frappe.session.user, "status": "Open"},
		[("description", _("Task"), ""), ("date", _("Date"), "date"), ("reference_name", _("Document"), "")],
		_("My open tasks"),
		order_by="date asc",
		empty=_("You have no open tasks."),
	)


def projects(context):
	require("Project")
	project = context.get("project")
	if project:
		doc = frappe.get_doc("Project", project)
		open_tasks = frappe.get_list(
			"Task",
			filters={"project": project, "status": ["not in", ["Completed", "Cancelled"]]},
			pluck="name",
		)
		answer = _("{0}: {1}% complete, status {2}, {3} open tasks, expected end {4}.").format(
			doc.project_name,
			number(doc.percent_complete),
			_(doc.status),
			number(len(open_tasks)),
			jdate(doc.expected_end_date) or "-",
		)
		return {"answer": answer, "actions": [link(_("Open"), get_url_to_form("Project", project))]}
	return document_list(
		"Project",
		{"status": "Open", "company": company()},
		[
			("name", _("Project"), "link"),
			("project_name", _("Name"), ""),
			("percent_complete", _("% Complete"), ""),
			("expected_end_date", _("Expected End"), "date"),
		],
		_("Open projects"),
		empty=_("No open projects."),
	)


def overdue_tasks(context):
	return document_list(
		"Task",
		{"status": ["not in", ["Completed", "Cancelled", "Template"]], "exp_end_date": ["<", nowdate()]},
		[
			("name", _("Task"), "link"),
			("subject", _("Subject"), ""),
			("project", _("Project"), ""),
			("exp_end_date", _("Expected End"), "date"),
		],
		_("Overdue tasks"),
		order_by="exp_end_date asc",
		empty=_("No overdue tasks."),
	)
