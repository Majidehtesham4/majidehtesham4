"""Logins from the chat: an investor's username and password, a login for a colleague or a customer
by what they do, and a new password. The work is done by iran_erp.users, as on the forms.

Nothing is final from the chat alone. A new login is made switched off (a draft): it works once
someone opens it in the ERP and ticks «فعال». Changing an existing login's username or password
is said back first and done only after a yes. The password the operator gives is never repeated.
"""

import frappe
from frappe import _

from iran_erp.commands.engine import NeedConfirm, NeedSlot


def _draft_answer(result, who) -> dict:
	return {
		"answer": _("A login was prepared for {0} with the username «{1}» and the password you gave, switched off.").format(
			who, result["username"]
		)
		+ "\n\n"
		+ _("To let them in, open it, check the roles and tick «Enabled». They then log in at {0}.").format(
			result["login_url"]
		),
		"actions": [{"label": _("Review and enable the login"), "url": f"/desk/user/{result['user']}"}],
	}


def _retry(error, context, question):
	"""A username taken or a password too short: ask for that one again."""
	text = frappe.utils.strip_html(str(error))
	slot = "password" if ("رمز" in text or "password" in text.lower()) else "username"
	context.values.pop(slot, None)
	frappe.clear_last_message()
	raise NeedSlot(slot, f"{text} {question}")


def create_investor_login(context):
	from iran_erp.users import investor_login

	from iran_erp.commands.handlers.insight import find_investors

	investor = context.get("investor")
	if not investor:
		typed = (context.get("name") or "").strip()
		found = find_investors(typed) if typed else []
		if len(found) == 1:
			investor = context.values["investor"] = found[0].name
		elif found:
			raise NeedSlot("investor", _("More than one investor has this name; which one?"), [(r.name, r.full_name) for r in found])
		elif typed:
			return {
				"answer": _("No investor named «{0}» was found; register them first, then ask again.").format(typed),
				"actions": [{"label": _("New Investor"), "url": f"/desk/iran-investor/new?full_name={typed}"}],
			}
		else:
			raise NeedSlot("investor", _("For which investor?"))
	if not context.get("password"):
		raise NeedSlot("password", _("Their password? (at least 6 characters; it is not shown again)"))
	if not context.get("username"):
		raise NeedSlot("username", _("Their username? (English letters, for example ali.rezaei)"))
	doc = frappe.get_doc("Iran Investor", investor)
	if doc.user and frappe.db.exists("User", doc.user) and not context.confirmed:
		raise NeedConfirm(
			_("{0} already has a login ({1}). Change its username to «{2}» and its password to the one you gave?").format(
				doc.full_name, frappe.db.get_value("User", doc.user, "username") or doc.user, context.get("username")
			)
		)
	try:
		result = investor_login(investor, context.get("username"), context.get("password"), enabled=0)
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as e:
		_retry(e, context, _("What should it be?"))
	if result.get("updated"):
		return {
			"answer": _("The username and password of {0} were changed.").format(doc.full_name),
			"actions": [{"label": doc.full_name, "url": f"/desk/user/{result['user']}"}],
		}
	return _draft_answer(result, _("investor {0}").format(doc.full_name))


def create_user_login(context):
	from iran_erp.commands.handlers.insight import find_investors
	from iran_erp.users import KINDS, create_user

	kind = context.get("kind")
	if not kind:
		options = [(key, _(label)) for key, (label, _roles) in KINDS.items()]
		options.append(("investor", _("Investor (sees only their own account)")))
		raise NeedSlot("kind", _("What does this person do? Their access comes from it."), options)
	if not context.get("name"):
		raise NeedSlot("name", _("Their full name?"))
	if kind == "investor":
		found = find_investors(context.get("name"))
		if len(found) != 1:
			raise NeedSlot(
				"investor",
				_("Which investor? (an investor's login shows their own account)"),
				[(r.name, r.full_name) for r in found] or None,
			)
		context.values["investor"] = found[0].name
	if not context.get("username"):
		raise NeedSlot("username", _("Their username? (English letters, for example ali.rezaei)"))
	if not context.get("password"):
		raise NeedSlot("password", _("Their password? (at least 6 characters; it is not shown again)"))
	if kind == "investor":
		return create_investor_login(context)
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
			enabled=0,
		)
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as e:
		_retry(e, context, _("What should it be?"))
	return _draft_answer(result, f"{context.get('name')} ({_(KINDS[kind][0])})")


def set_user_password(context):
	from iran_erp.users import find_user, set_password

	name = find_user(context.get("user")) or context.get("user")
	full_name = frappe.db.get_value("User", name, "full_name") or name
	if not context.confirmed:
		raise NeedConfirm(_("Change the password of {0} to the one you gave?").format(full_name))
	try:
		result = set_password(name, context.get("password"))
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as e:
		_retry(e, context, _("What should it be?"))
	return {
		"answer": _("The password of {0} was changed.").format(full_name),
		"actions": [{"label": full_name, "url": f"/desk/user/{result['user']}"}],
	}
