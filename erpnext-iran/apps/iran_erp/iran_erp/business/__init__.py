"""Business packs: the system set up for one kind of business.

The easy setup asks what the business is. A pack then adds what that business needs on top of
the common parts (accounting, cheques, buying and selling): its own pages on the home screen,
the accounts its documents post to, and hides the parts it does not use. Packs are code, so a
new kind of business is a new entry in PACKS.

Branches work for any business: each branch is a Branch record, and Branch is an accounting
dimension, so every entry can carry its branch and reports can be filtered by it.
"""

import frappe
from frappe import _

# key: (account number, account name, number of the parent group, account type, root type)
ACCOUNTS = {
	"vehicle_stock": ("1504", "موجودی خودرو", "15", "", "Asset"),
	"investors": ("3207", "حساب سرمایه‌گذاران", "32", "Payable", "Liability"),
	"deferred_interest": ("3702", "سود تحقق‌نیافته فروش اقساطی", "37", "", "Liability"),
	"vehicle_sales": ("6104", "فروش خودرو", "61", "Income Account", "Income"),
	"instalment_income": ("6202", "درآمد سود فروش اقساطی", "62", "Income Account", "Income"),
	"fee_income": ("6203", "درآمد کارمزد و جریمه دیرکرد", "62", "Income Account", "Income"),
	"commission_income": ("6204", "درآمد حق‌العمل فروش امانی", "62", "Income Account", "Income"),
	"investor_profit": ("8203", "هزینه سود سرمایه‌گذاران", "82", "Expense Account", "Expense"),
	"cost_of_sales": ("7101", "بهای تمام‌شده کالای فروش‌رفته", "71", "Cost of Goods Sold", "Expense"),
}

INVESTOR_GROUP = "سرمایه‌گذاران"
INVESTOR_ROLE = "Investor"

# label, link, image, roles: home-screen icons of a pack's pages
DEALERSHIP_ICONS = (
	("Vehicles", "/desk/iran-vehicle", "vehicles.svg", ("System Manager", "Accounts Manager", "Sales User")),
	(
		"Instalment Sales",
		"/desk/iran-instalment-sale",
		"instalments.svg",
		("System Manager", "Accounts Manager", "Accounts User", "Sales User"),
	),
	(
		"Investors",
		"/desk/iran-investment-contract",
		"investors.svg",
		("System Manager", "Accounts Manager", "Accounts User"),
	),
	(
		"Cash Forecast",
		"/desk/query-report/Instalments and Investors Cash Forecast",
		"forecast.svg",
		("System Manager", "Accounts Manager", "Accounts User"),
	),
)

INVESTOR_ICON = ("My Account", "/desk/iran-my-account", "investors.svg", (INVESTOR_ROLE,))

PACKS = {
	"Car Dealership": {
		"label": "نمایشگاه خودرو",
		"icons": DEALERSHIP_ICONS,
		# Home-screen icons of parts a car dealership does not use
		"hide": ("Manufacturing", "Projects", "Quality", "Support", "Assets"),
		"accounts": tuple(ACCOUNTS),
	},
}


def account(company: str, key: str) -> str:
	"""The company's account for one of the pack accounts, made the first time it is needed."""
	number, name, parent_number, account_type, root_type = ACCOUNTS[key]
	existing = frappe.db.get_value(
		"Account", {"company": company, "account_number": number, "is_group": 0}, "name"
	)
	if existing:
		return existing
	parent = frappe.db.get_value(
		"Account", {"company": company, "account_number": parent_number, "is_group": 1}, "name"
	) or frappe.db.get_value(
		"Account",
		{"company": company, "root_type": root_type, "is_group": 1, "parent_account": ("is", "not set")},
		"name",
	)
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"account_name": name,
			"account_number": number,
			"parent_account": parent,
			"account_type": account_type,
			"is_group": 0,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def investor_group(company: str | None = None) -> str:
	"""The supplier group of investors, whose money is owed to them in the investors' account."""
	if not frappe.db.exists("Supplier Group", INVESTOR_GROUP):
		parent = frappe.db.get_value("Supplier Group", {"is_group": 1}, "name", order_by="lft asc")
		frappe.get_doc(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": INVESTOR_GROUP,
				"parent_supplier_group": parent,
			}
		).insert(ignore_permissions=True)
	if company:
		group = frappe.get_doc("Supplier Group", INVESTOR_GROUP)
		if not any(row.company == company for row in group.accounts):
			group.append("accounts", {"company": company, "account": account(company, "investors")})
			group.flags.ignore_permissions = True
			group.save()
	return INVESTOR_GROUP


def ensure_role():
	if not frappe.db.exists("Role", INVESTOR_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": INVESTOR_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def apply_pack(pack: str, company: str):
	"""Set the system up for one kind of business."""
	from iran_erp.desktop import add_icons, clear_every_users_desktop_icons

	spec = PACKS[pack]
	for key in spec["accounts"]:
		account(company, key)
	investor_group(company)
	ensure_role()
	add_icons(spec["icons"] + (INVESTOR_ICON,))
	for label in spec["hide"]:
		if frappe.db.exists("Desktop Icon", label):
			frappe.db.set_value("Desktop Icon", label, "hidden", 1)
	clear_every_users_desktop_icons()


def set_branches(names: list[str], company: str | None = None):
	"""Branch records for the names given, and Branch as an accounting dimension once there are any."""
	names = [n.strip() for n in names if n and n.strip()]
	for name in names:
		if not frappe.db.exists("Branch", name):
			frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True)
	if names and not frappe.db.exists("Accounting Dimension", {"document_type": "Branch"}):
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
			make_dimension_in_accounting_doctypes,
		)

		dimension = frappe.get_doc(
			{"doctype": "Accounting Dimension", "document_type": "Branch", "label": "Branch"}
		)
		# ERPNext adds the branch fields to every accounting document in a background job; entries
		# made before it runs would fail, so they are added now
		dimension.insert(ignore_permissions=True)
		make_dimension_in_accounting_doctypes(doc=dimension)
	return names


def journal(company, posting_date, rows, remark, branch=None, voucher_type="Journal Entry"):
	"""A submitted journal entry from rows of {account, debit|credit, party_type, party}."""
	has_branch = branch and frappe.get_meta("Journal Entry Account").has_field("branch")
	accounts = []
	for row in rows:
		amount_debit, amount_credit = flt2(row.pop("debit", 0)), flt2(row.pop("credit", 0))
		if not (amount_debit or amount_credit):
			continue
		line = {**row, "debit_in_account_currency": amount_debit, "credit_in_account_currency": amount_credit}
		if has_branch:
			line["branch"] = branch
		accounts.append(line)
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": voucher_type,
			"company": company,
			"posting_date": posting_date,
			"user_remark": remark,
			"accounts": accounts,
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry.name


def party_account(party_type, party, company):
	from erpnext.accounts.party import get_party_account

	return get_party_account(party_type, party, company)


def cancel_entries(*names):
	for name in names:
		if name and frappe.db.get_value("Journal Entry", name, "docstatus") == 1:
			entry = frappe.get_doc("Journal Entry", name)
			entry.flags.ignore_permissions = True
			entry.cancel()


def flt2(value):
	from frappe.utils import flt

	return flt(value, 0)


def require_cash_account(account_name, company):
	if not account_name:
		return
	details = frappe.db.get_value(
		"Account", account_name, ["company", "account_type", "is_group"], as_dict=True
	)
	if (
		not details
		or details.company != company
		or details.is_group
		or details.account_type not in ("Bank", "Cash")
	):
		frappe.throw(_("{0} is not a bank or cash account of {1}").format(account_name, company))


def after_migrate():
	"""The investor role, and the pages of a business pack already chosen (new icons of an update)."""
	ensure_role()
	# The investor's page was first named after the Iran Investor list, whose address it took
	if frappe.db.exists("Page", "iran-investor"):
		frappe.delete_doc("Page", "iran-investor", ignore_permissions=True, force=True)
	business_type = frappe.db.get_single_value("Iran Setup", "business_type")
	company = frappe.defaults.get_global_default("company")
	if business_type in PACKS and company:
		apply_pack(business_type, company)
