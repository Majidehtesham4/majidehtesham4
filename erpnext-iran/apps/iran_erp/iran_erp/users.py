"""Logins for the people around the business, by what they do: staff, branch and general managers,
customers and investors. Each signs in with a username (or email) and password.

The assistant, the AI model and the forms (an investor's «ساخت دسترسی ورود») all make logins here,
so a login is made the same way wherever it is asked for.
"""

import re

import frappe
from frappe import _
from frappe.utils.password import update_password

from iran_erp.business import INVESTOR_ROLE, RECEPTION_ROLE, ensure_role

# What someone does → the roles their login gets. Branch staff and managers work at one branch.
KINDS = {
	"reception": ("Car reception", (RECEPTION_ROLE,)),
	"sales": ("Salesperson", ("Sales User",)),
	"accountant": ("Accountant", ("Accounts User",)),
	"accounts_manager": ("Head of accounts", ("Accounts Manager", "Accounts User")),
	"branch_manager": (
		"Branch manager",
		("Sales Manager", "Sales User", "Accounts User", "Purchase User", "Stock User", RECEPTION_ROLE),
	),
	"general_manager": (
		"General manager",
		(
			"Sales Manager",
			"Sales User",
			"Accounts Manager",
			"Accounts User",
			"Purchase Manager",
			"Purchase User",
			"Stock Manager",
			"Stock User",
			RECEPTION_ROLE,
		),
	),
	"customer": ("Customer (sees their own invoices on the website)", ("Customer",)),
}
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
# A login without an email of its own gets an address that no mail goes to
NO_MAIL_DOMAIN = "users.invalid"


def _can_manage(investor=False):
	roles = ("System Manager", "Accounts Manager") if investor else ("System Manager",)
	frappe.only_for(roles)


def normal_username(username: str) -> str:
	from iran_erp.utils.national_id import normalize_digits

	username = normalize_digits(username or "").strip().lower()
	if not USERNAME.match(username):
		frappe.throw(
			_("The username is 3 to 40 English letters or digits (dots, dashes and _ too), for example: ali.rezaei")
		)
	return username


def check_password(password: str) -> str:
	password = (password or "").strip()
	if len(password) < 6:
		frappe.throw(_("The password needs at least 6 characters"))
	return password


def allow_username_login():
	if not frappe.db.get_single_value("System Settings", "allow_login_using_user_name"):
		frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)


def _new_user(full_name, username, password, roles, email=None, mobile=None, website=False):
	username = normal_username(username)
	password = check_password(password)
	email = (email or "").strip().lower() or f"{username}@{NO_MAIL_DOMAIN}"
	if frappe.db.exists("User", {"username": username}) or frappe.db.exists("User", email):
		frappe.throw(_("The username {0} is taken; choose another").format(username))
	names = (full_name or username).strip().split(" ", 1)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"username": username,
			"first_name": names[0],
			"last_name": names[1] if len(names) > 1 else "",
			"mobile_no": mobile,
			"user_type": "Website User" if website else "System User",
			"language": "fa",
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	)
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = True
	user.insert()
	update_password(user.name, password)
	allow_username_login()
	return user


def _result(user, password_set=True):
	return {
		"user": user.name,
		"username": user.username,
		"login_url": (frappe.request.host_url.rstrip("/") if getattr(frappe.local, "request", None) else frappe.utils.get_url())
		+ "/login",
		"password_set": password_set,
	}


@frappe.whitelist()
def create_user(
	full_name: str,
	username: str,
	password: str,
	kind: str,
	email: str | None = None,
	mobile: str | None = None,
	branch: str | None = None,
) -> dict:
	"""A login for someone who works with the business (or a customer), by what they do."""
	_can_manage()
	if kind not in KINDS:
		frappe.throw(_("Choose what this person does: {0}").format("، ".join(_(k[0]) for k in KINDS.values())))
	ensure_role()
	if branch and not frappe.db.exists("Branch", branch):
		frappe.throw(_("There is no branch {0}").format(branch))
	user = _new_user(full_name, username, password, KINDS[kind][1], email, mobile, website=kind == "customer")
	if kind == "customer":
		_link_customer(user, full_name)
	# Staff of a branch work at that branch; a general manager has none (they see every branch)
	if branch and kind != "general_manager":
		frappe.db.set_value("User", user.name, "iran_branch", branch)
	return _result(user)


def _link_customer(user, full_name):
	"""A customer's login sees that customer's orders and invoices on the website."""
	customer = frappe.db.get_value("Customer", {"customer_name": full_name}) if full_name else None
	if customer:
		doc = frappe.get_doc("Customer", customer)
		doc.append("portal_users", {"user": user.name})
		doc.flags.ignore_permissions = True
		doc.save()


@frappe.whitelist()
def set_password(user: str, password: str) -> dict:
	"""A new password for a login (found by its username, email or name)."""
	_can_manage(investor=True)
	name = find_user(user)
	if not name:
		frappe.throw(_("No login was found for {0}").format(user))
	if name == "Administrator" and frappe.session.user != "Administrator":
		frappe.throw(_("Only the Administrator changes their own password"))
	# Heads of accounts change investors' passwords only
	if "System Manager" not in frappe.get_roles() and INVESTOR_ROLE not in frappe.get_roles(name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	update_password(name, check_password(password))
	return _result(frappe.get_doc("User", name))


def find_user(text: str) -> str | None:
	text = (text or "").strip()
	if not text:
		return None
	for filters in ({"name": text}, {"username": text.lower()}, {"email": text.lower()}, {"full_name": text}):
		name = frappe.db.get_value("User", filters)
		if name:
			return name
	return None


@frappe.whitelist()
def investor_login(investor: str, username: str, password: str, email: str | None = None) -> dict:
	"""The investor's login: it opens on their own account (contracts, profit, cheques, cars) and
	shows nothing else. An investor who has one gets the new username and password instead."""
	_can_manage(investor=True)
	ensure_role()
	doc = frappe.get_doc("Iran Investor", investor)
	if doc.user and frappe.db.exists("User", doc.user):
		username = normal_username(username)
		taken = frappe.db.get_value("User", {"username": username, "name": ("!=", doc.user)})
		if taken:
			frappe.throw(_("The username {0} is taken; choose another").format(username))
		frappe.db.set_value("User", doc.user, {"username": username, "enabled": 1})
		update_password(doc.user, check_password(password))
		user = frappe.get_doc("User", doc.user)
		if INVESTOR_ROLE not in frappe.get_roles(user.name):
			user.add_roles(INVESTOR_ROLE)
		allow_username_login()
		return {**_result(user), "updated": True}
	user = _new_user(doc.full_name, username, password, (INVESTOR_ROLE,), email or None, doc.mobile)
	doc.db_set("user", user.name)
	return {**_result(user), "created": True}


def link_investor(doc, method=None):
	"""User on_update: a login given the investor role by hand is linked to its investor (by name
	or mobile), so it opens on that investor's account."""
	if INVESTOR_ROLE not in [r.role for r in doc.get("roles", [])]:
		return
	if frappe.db.exists("Iran Investor", {"user": doc.name}):
		return
	for filters in ({"mobile": doc.mobile_no}, {"full_name": doc.full_name}):
		if not all(filters.values()):
			continue
		investor = frappe.db.get_value("Iran Investor", {**filters, "user": ("is", "not set")})
		if investor:
			frappe.db.set_value("Iran Investor", investor, "user", doc.name)
			return
