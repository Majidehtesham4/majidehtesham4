"""Logins from the chat: an investor's username and password, a login for a colleague or a
customer by what they do, and a new password. The work is done by iran_erp.users, as on the forms."""

import frappe
from frappe import _

from iran_erp.commands.engine import NeedSlot


def _login_note(result) -> str:
	return _("They log in at {0} with the username «{1}» and the password you gave.").format(
		result["login_url"], result["username"]
	)


def _retry(error, slot, question):
	"""A username taken or a password too short: ask for that one again."""
	frappe.clear_last_message()
	raise NeedSlot(slot, f"{frappe.utils.strip_html(str(error))} {question}")


def create_investor_login(context):
	from iran_erp.users import investor_login

	investor = context.get("investor")
	try:
		result = investor_login(investor, context.get("username"), context.get("password"))
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as e:
		slot = "password" if "رمز" in str(e) or "password" in str(e).lower() else "username"
		context.values.pop(slot, None)
		_retry(e, slot, _("What should it be?"))
	name = frappe.db.get_value("Iran Investor", investor, "full_name")
	done = (
		_("The login of investor {0} now has this username and password.")
		if result.get("updated")
		else _("A login was made for investor {0}; it opens on their own account (contracts, profit, cheques, cars, statement).")
	)
	return {
		"answer": done.format(name) + "\n\n" + _login_note(result),
		"actions": [
			{"label": _("Investor's Account"), "url": "/app/iran-my-account"},
			{"label": name, "url": f"/app/iran-investor/{investor}"},
		],
	}


def create_user_login(context):
	from iran_erp.users import KINDS, create_user

	kind = context.get("kind")
	if not kind:
		raise NeedSlot(
			"kind",
			_("What does this person do?"),
			[(key, _(label)) for key, (label, _roles) in KINDS.items()],
		)
	if not context.get("name"):
		raise NeedSlot("name", _("Their full name?"))
	if not context.get("username"):
		raise NeedSlot("username", _("Their username? (English letters, for example ali.rezaei)"))
	if not context.get("password"):
		raise NeedSlot("password", _("Their password? (at least 6 characters)"))
	branches = frappe.get_all("Branch", pluck="name")
	if kind in ("reception", "sales", "branch_manager") and len(branches) > 1 and not context.get("branch"):
		raise NeedSlot("branch", _("Which branch do they work at?"), [(b, b) for b in branches])
	try:
		result = create_user(
			context.get("name"),
			context.get("username"),
			context.get("password"),
			kind,
			branch=context.get("branch") or (branches[0] if len(branches) == 1 else None),
		)
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as e:
		slot = "password" if "رمز" in str(e) or "password" in str(e).lower() else "username"
		context.values.pop(slot, None)
		_retry(e, slot, _("What should it be?"))
	return {
		"answer": _("A login was made for {0} ({1}).").format(context.get("name"), _(KINDS[kind][0]))
		+ "\n\n"
		+ _login_note(result),
		"actions": [{"label": context.get("name"), "url": f"/app/user/{result['user']}"}],
	}


def set_user_password(context):
	from iran_erp.users import set_password

	try:
		result = set_password(context.get("user"), context.get("password"))
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as e:
		context.values.pop("password", None)
		_retry(e, "password", _("What should it be?"))
	name = frappe.db.get_value("User", result["user"], "full_name") or result["user"]
	return {
		"answer": _("The password of {0} was changed.").format(name) + "\n\n" + _login_note(result),
		"actions": [{"label": name, "url": f"/app/user/{result['user']}"}],
	}
