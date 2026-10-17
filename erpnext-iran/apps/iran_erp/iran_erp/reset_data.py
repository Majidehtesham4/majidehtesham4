"""Start over in a test system: every document and every customer, supplier, item, car, cheque and
contract is deleted, numbering starts again from 1 and Easy Setup asks about the business again.

What stays is what the system is built on: the companies with their chart of accounts, fiscal
years, warehouses and cost centres, the users, the settings, and the lists the business packs
fill (car models, colours, services...). For a system with nothing at all, make the site again
(deploy/reset.ps1, or deploy/business.ps1 for one business's environment).
"""

import json
import re

import frappe
from frappe import _

STATUS_KEY = "iran_reset_data_job"
CONFIRM = "حذف همه"

# Documents and the records they are made of, children before what they belong to
DOCTYPES = (
	# Ledgers and what writes them
	"GL Entry",
	"Payment Ledger Entry",
	"Stock Ledger Entry",
	"Serial and Batch Bundle",
	"Serial No",
	"Batch",
	"Bin",
	"Repost Item Valuation",
	"Repost Payment Ledger",
	"Repost Accounting Ledger",
	"Journal Entry",
	"Payment Entry",
	"Payment Request",
	"Payment Order",
	"Dunning",
	"Period Closing Voucher",
	"Exchange Rate Revaluation",
	"Invoice Discounting",
	"Loyalty Point Entry",
	"Process Payment Reconciliation",
	"Bank Transaction",
	"Bank Statement Import",
	"Bank Guarantee",
	"Bank Account",
	"Budget",
	# Selling and buying
	"Sales Invoice",
	"Purchase Invoice",
	"POS Invoice",
	"POS Opening Entry",
	"POS Closing Entry",
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Supplier Quotation",
	"Request for Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Material Request",
	"Blanket Order",
	"Pick List",
	"Packing Slip",
	"Installation Note",
	"Pricing Rule",
	"Promotional Scheme",
	"Coupon Code",
	# Stock and production
	"Stock Entry",
	"Stock Reconciliation",
	"Landed Cost Voucher",
	"Quality Inspection",
	"Shipment",
	"Putaway Rule",
	"Job Card",
	"Work Order",
	"Production Plan",
	"BOM",
	"Asset Movement",
	"Asset Repair",
	"Asset Value Adjustment",
	"Asset Capitalization",
	"Asset Depreciation Schedule",
	"Asset",
	# People, items and work
	"Item Price",
	"Item",
	"Opportunity",
	"Prospect",
	"Lead",
	"Customer",
	"Supplier",
	"Contact",
	"Address",
	"Timesheet",
	"Task",
	"Project",
	"Issue",
	"Warranty Claim",
	"Maintenance Visit",
	"Maintenance Schedule",
	"Employee",
	"Event",
	"Note",
	"Web Page",
	# This app's records
	"Iran Car Inquiry",
	"Iran Instalment Sale",
	"Iran Investment Contract",
	"Iran Cheque",
	"Iran Vehicle",
	"Iran Investor",
	"Iran Parking",
	"Branch",
)
# Records of these that stay: the company's own address, and the contacts of the users
KEEP = {"Address": "ifnull(is_your_company_address, 0) = 0", "Contact": "ifnull(user, '') = ''"}
# What was said and kept about the deleted records
TRAILS = ("Comment", "Version", "Communication", "File", "ToDo", "Notification Log", "Deleted Document")


@frappe.whitelist()
def start(confirm: str):
	"""Delete everything in the background; the page asks status() how it went."""
	frappe.only_for("System Manager")
	if (confirm or "").strip() != CONFIRM:
		frappe.throw(_("Type «{0}» to confirm").format(CONFIRM))
	_set_status({"running": True})
	frappe.enqueue("iran_erp.reset_data.run_job", queue="long", timeout=3600, enqueue_after_commit=True)
	return {"started": True}


@frappe.whitelist()
def status() -> dict:
	frappe.only_for("System Manager")
	# Read from the table itself: the cached defaults can lag behind the background job
	value = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": STATUS_KEY}, "defvalue")
	return json.loads(value or '{"running": false}')


def run_job():
	result = {"running": False}
	try:
		result["count"] = delete_all_data()
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Iran ERP: delete all data")
		result["error"] = frappe.utils.strip_html(str(e))
	_set_status(result)


def delete_all_data() -> int:
	"""Deletes the records of DOCTYPES with their children and trails, restarts their numbering
	and resets Easy Setup. Returns how many records were deleted."""
	deleted = 0
	prefixes = set()
	for doctype in DOCTYPES:
		if not frappe.db.exists("DocType", doctype) or not frappe.db.table_exists(doctype):
			continue
		where = KEEP.get(doctype, "1 = 1")
		names = frappe.db.sql_list(f"select name from `tab{doctype}` where {where}")
		if not names:
			continue
		for name in names:
			match = re.match(r"^(.*?)(\d+)$", str(name))
			if match and match.group(1):
				prefixes.add(match.group(1))
		for child in {df.options for df in frappe.get_meta(doctype).get_table_fields()}:
			if frappe.db.table_exists(child):
				frappe.db.sql(
					f"""delete from `tab{child}` where parenttype = %s
					and parent in (select name from `tab{doctype}` where {where})""",
					doctype,
				)
		frappe.db.sql(f"delete from `tab{doctype}` where {where}")
		for trail in TRAILS:
			field = "attached_to_doctype" if trail == "File" else "reference_doctype"
			if trail == "Version":
				field = "ref_doctype"
			if trail == "Notification Log":
				field = "document_type"
			if frappe.db.table_exists(trail) and frappe.get_meta(trail).has_field(field):
				frappe.db.delete(trail, {field: doctype})
		deleted += len(names)
	for trail in ("ToDo", "Notification Log", "Deleted Document"):
		frappe.db.delete(trail)
	# Numbering starts again from 1
	if prefixes:
		frappe.db.delete("Series", {"name": ("in", list(prefixes))})
	_reset_setup()
	frappe.db.commit()
	frappe.clear_cache()
	return deleted


def _reset_setup():
	"""Easy Setup asks about the business again; sample data is no longer there."""
	setup = frappe.get_single("Iran Setup")
	for field in (
		"business_type",
		"branches",
		"business_features",
		"parkings",
		"steps_done",
		"data",
		"opening_documents",
	):
		setup.set(field, None)
	setup.opening_posted = 0
	setup.flags.ignore_validate = setup.flags.ignore_mandatory = True
	setup.save(ignore_permissions=True)
	showroom = frappe.get_single("Iran Showroom Settings")
	showroom.experts = []
	showroom.flags.ignore_validate = showroom.flags.ignore_mandatory = True
	showroom.save(ignore_permissions=True)
	for key in ("iran_demo_records", "iran_dealership_demo_records"):
		# Empty, as their own delete leaves them
		frappe.db.set_default(key, "")


def _set_status(status: dict):
	frappe.db.set_default(STATUS_KEY, json.dumps(status, ensure_ascii=False))
	frappe.db.commit()
