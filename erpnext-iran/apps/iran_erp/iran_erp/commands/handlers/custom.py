"""Commands an administrator defined in Iran Chat Command."""

import json

import frappe
from frappe import _

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands.handlers import link, list_url, report_url, require
from iran_erp.commands.text import today
from iran_erp.utils.jalali import format_jalali


def run(name: str, message) -> dict:
	command = frappe.get_cached_doc("Iran Chat Command", name)
	reply = (
		(command.reply or "")
		.replace("{today}", format_jalali(today()))
		.replace("{user}", frappe.utils.get_fullname(frappe.session.user))
	)
	target = (command.target or "").strip()
	filters = json.loads(command.filters or "{}") if command.filters else None
	url = None
	if command.action == "Open List" and target:
		require(target)
		url = list_url(target, filters)
	elif command.action == "New Document" and target:
		require(target, "create")
		url = list_url(target) + "/new"
	elif command.action == "Open Report" and target:
		url = report_url(target, filters)
	elif command.action == "Open Document" and target:
		doctype, _sep, docname = target.partition(":")
		url = get_url_to_form(doctype, docname)
	elif command.action == "Open Link" and target:
		url = target
	actions = [{**link(command.command_name, url), "open": True}] if url else []
	return {"answer": reply or command.command_name, "actions": actions}
