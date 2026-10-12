"""The Iranian chart of accounts (کدینگ حسابداری) and VAT tax templates."""

import json
import os
import shutil

import frappe
from frappe.utils import flt

CHART_NAME = "کدینگ حسابداری ایران"
CHART_FILE = os.path.join(os.path.dirname(__file__), "ir_iran_chart_of_accounts.json")
DEFAULT_VAT_RATE = 10

# Company default account fields, by account number in the chart
COMPANY_DEFAULTS = {
	"default_receivable_account": "1301",
	"default_payable_account": "3101",
	"default_cash_account": "1101",
	"default_bank_account": "110301",
	"default_income_account": "6101",
	"default_expense_account": "7101",
	"round_off_account": "8301",
	"write_off_account": "8113",
	"exchange_gain_loss_account": "6303",
	"unrealized_exchange_gain_loss_account": "6303",
	"disposal_account": "6302",
	"depreciation_expense_account": "8111",
	"accumulated_depreciation_account": "2202",
	"capital_work_in_progress_account": "2107",
	"asset_received_but_not_billed": "3802",
	"stock_received_but_not_billed": "3801",
	"default_inventory_account": "1501",
	"stock_adjustment_account": "7104",
	"default_provisional_account": "3803",
}

SALES_VAT_ACCOUNT = "3301"
PURCHASE_VAT_ACCOUNT = "1701"


def get_chart_tree() -> dict:
	with open(CHART_FILE) as f:
		return json.load(f)["tree"]


def install_chart_template():
	"""ERPNext only offers charts from its own folder; put ours there so the setup wizard lists it."""
	try:
		from erpnext.accounts.doctype.account.chart_of_accounts import verified

		target = os.path.join(os.path.dirname(verified.__file__), os.path.basename(CHART_FILE))
		if not os.path.exists(target) or open(target).read() != open(CHART_FILE).read():
			shutil.copyfile(CHART_FILE, target)
	except OSError:
		# Read-only app folder: the Docker image copies the file at build time instead
		pass


@frappe.whitelist()
def apply_iran_chart(company: str, vat_rate: float | None = None):
	"""Replace the chart of accounts of a company that has no transactions yet with the Iranian one."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
	from erpnext.accounts.doctype.chart_of_accounts_importer.chart_of_accounts_importer import (
		set_default_accounts,
		unset_existing_data,
		validate_company,
	)

	# Refuses companies with GL entries, the same rule as ERPNext's chart importer
	validate_company(company)
	unset_existing_data(company)
	clear_dangling_account_links()

	frappe.local.flags.ignore_root_company_validation = True
	create_charts(company, custom_chart=get_chart_tree())
	frappe.db.set_value("Company", company, "chart_of_accounts", CHART_NAME)
	if vat_rate not in (None, ""):
		frappe.flags.iran_vat_rate = flt(vat_rate)
	# Saves the company, which runs on_company_update below, then adds ERPNext's own tax template
	set_default_accounts(company)
	remove_stray_tax_setup(company)
	return {"accounts": frappe.db.count("Account", {"company": company})}


def on_company_update(doc, method=None):
	"""Fill company defaults and VAT templates once a company is on the Iranian chart."""
	if doc.chart_of_accounts != CHART_NAME:
		return
	sales_account = get_account(doc.name, SALES_VAT_ACCOUNT)
	# Only right after the chart is created; later changes to defaults and templates are the user's
	if not sales_account or has_vat_template(doc.name, sales_account):
		return
	# ERPNext picks the first account of each type, which is not always the main one here
	set_company_defaults(doc.name, overwrite=True)
	remove_stray_tax_setup(doc.name)
	create_vat_templates(doc.name)


def get_account(company: str, account_number: str) -> str | None:
	return frappe.db.get_value("Account", {"company": company, "account_number": account_number})


def set_company_defaults(company: str, overwrite: bool = False):
	meta = frappe.get_meta("Company")
	current = frappe.db.get_value("Company", company, list(COMPANY_DEFAULTS), as_dict=True)
	values = {}
	for fieldname, number in COMPANY_DEFAULTS.items():
		if not meta.has_field(fieldname) or (current.get(fieldname) and not overwrite):
			continue
		account = get_account(company, number)
		if account:
			values[fieldname] = account
	if values:
		frappe.db.set_value("Company", company, values)

	company_doc = frappe.get_doc("Company", company)
	if not company_doc.default_cash_account:
		return
	cash_mode = frappe.db.get_value("Mode of Payment", {"type": "Cash"})
	if overwrite and cash_mode:
		frappe.db.set_value(
			"Mode of Payment Account",
			{"parent": cash_mode, "company": company},
			"default_account",
			company_doc.default_cash_account,
		)
	company_doc.set_mode_of_payment_account()


def vat_rate_setting() -> float:
	rate = frappe.db.get_singles_dict("Iran ERP Settings").get("vat_rate")
	return flt(rate) if rate not in (None, "") else DEFAULT_VAT_RATE


def create_vat_templates(company: str, rate: float | None = None):
	"""Sales and purchase VAT templates, plus an exempt item tax template. Existing ones are kept."""
	if rate is None:
		rate = frappe.flags.iran_vat_rate if frappe.flags.iran_vat_rate is not None else vat_rate_setting()
	rate = flt(rate)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	sales_account = get_account(company, SALES_VAT_ACCOUNT)
	purchase_account = get_account(company, PURCHASE_VAT_ACCOUNT)
	if not (sales_account and purchase_account):
		return

	# Account names in the chart are Persian whatever the user's language, so the templates are too
	title = f"مالیات بر ارزش افزوده {rate:g}%"
	description = "مالیات و عوارض ارزش افزوده"

	if not frappe.db.exists("Sales Taxes and Charges Template", f"{title} - {abbr}"):
		frappe.get_doc(
			{
				"doctype": "Sales Taxes and Charges Template",
				"title": title,
				"company": company,
				"is_default": not has_default("Sales Taxes and Charges Template", company),
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": sales_account,
						"description": description,
						"rate": rate,
					}
				],
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Purchase Taxes and Charges Template", f"{title} - {abbr}"):
		frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": title,
				"company": company,
				"is_default": not has_default("Purchase Taxes and Charges Template", company),
				"taxes": [
					{
						"category": "Total",
						"add_deduct_tax": "Add",
						"charge_type": "On Net Total",
						"account_head": purchase_account,
						"description": description,
						"rate": rate,
					}
				],
			}
		).insert(ignore_permissions=True)

	exempt = "معاف از مالیات بر ارزش افزوده"
	if not frappe.db.exists("Item Tax Template", f"{exempt} - {abbr}"):
		frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": exempt,
				"company": company,
				"taxes": [
					{"tax_type": sales_account, "tax_rate": 0},
					{"tax_type": purchase_account, "tax_rate": 0},
				],
			}
		).insert(ignore_permissions=True)


def has_vat_template(company: str, sales_account: str) -> bool:
	templates = frappe.get_all("Sales Taxes and Charges Template", {"company": company}, pluck="name")
	return bool(
		templates
		and frappe.db.exists(
			"Sales Taxes and Charges",
			{
				"account_head": sales_account,
				"parent": ("in", templates),
				"parenttype": "Sales Taxes and Charges Template",
			},
		)
	)


def remove_stray_tax_setup(company: str):
	"""ERPNext adds a 7% "Iran Tax" template on a "VAT" account of its own; the chart has its own VAT accounts."""
	stray = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_number": ("is", "not set")},
		pluck="name",
	)

	# Item tax templates whose accounts were deleted with the old chart
	for name in frappe.get_all("Item Tax Template", {"company": company}, pluck="name"):
		tax_types = frappe.get_all("Item Tax Template Detail", {"parent": name}, pluck="tax_type")
		if not any(tax_types):
			frappe.delete_doc("Item Tax Template", name, ignore_permissions=True, force=True)

	if not stray or frappe.db.exists("GL Entry", {"account": ("in", stray)}):
		return
	for template, child in (
		("Sales Taxes and Charges Template", "Sales Taxes and Charges"),
		("Purchase Taxes and Charges Template", "Purchase Taxes and Charges"),
		("Item Tax Template", "Item Tax Template Detail"),
	):
		account_field = "tax_type" if template == "Item Tax Template" else "account_head"
		parents = frappe.get_all(
			child, filters={account_field: ("in", stray), "parenttype": template}, pluck="parent"
		)
		for name in set(parents):
			frappe.delete_doc(template, name, ignore_permissions=True, force=True)
	for account in stray:
		frappe.delete_doc("Account", account, ignore_permissions=True, force=True)


def has_default(doctype: str, company: str) -> bool:
	return bool(frappe.db.exists(doctype, {"company": company, "is_default": 1}))


def clear_dangling_account_links():
	"""Clear links (item defaults, warehouses and the like) to accounts that were just deleted."""
	fields = frappe.get_all(
		"DocField", filters={"fieldtype": "Link", "options": "Account"}, fields=["parent", "fieldname"]
	) + frappe.get_all(
		"Custom Field",
		filters={"fieldtype": "Link", "options": "Account"},
		fields=["dt as parent", "fieldname"],
	)
	for field in fields:
		meta = frappe.get_meta(field.parent)
		if meta.issingle or meta.is_virtual or field.parent == "Account":
			continue
		if not frappe.db.has_column(field.parent, field.fieldname):
			continue
		frappe.db.sql(
			f"""update `tab{field.parent}` set `{field.fieldname}` = null
			where ifnull(`{field.fieldname}`, '') != ''
			and `{field.fieldname}` not in (select name from `tabAccount`)"""
		)
