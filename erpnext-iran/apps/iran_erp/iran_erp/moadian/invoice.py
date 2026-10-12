"""Build the Moadian (سامانه مؤدیان) electronic invoice for a sales invoice.

This prepares the tax number and the invoice data in the field names of the tax organization's
invoice format. Signing the data with the taxpayer's key and sending it is not done here and has
not been tested against the live service.
"""

import datetime
import json

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate

from iran_erp.moadian.tax_id import generate_tax_id
from iran_erp.utils.national_id import normalize_digits

# Invoice subject (ins)
ORIGINAL, RETURN = 1, 4
# Settlement method (setm)
CASH, CREDIT, MIXED = 1, 2, 3


def _rial(value) -> int:
	return round(flt(value))


def _ms(value) -> int:
	return int(get_datetime(value).timestamp() * 1000)


def buyer_type(national_id: str) -> int | None:
	"""tob: 1 for a person (10-digit national code), 2 for a legal entity (11-digit national ID)."""
	digits = normalize_digits(national_id or "")
	return {10: 1, 11: 2}.get(len(digits)) if digits.isdigit() else None


def item_vat_rate(item, vat_rates: dict) -> float:
	"""The VAT rate of a line: from its item tax template if it has one, else the invoice's rate."""
	item_rates = json.loads(item.get("item_tax_rate") or "{}")
	for account in vat_rates:
		if account in item_rates:
			return flt(item_rates[account])
	return flt(next(iter(vat_rates.values()), 0))


def build_payload(invoice, seller: dict, buyer: dict, item_codes: dict, unit_codes: dict, settings: dict):
	"""Return (payload, problems). Problems are the reasons the tax organization would reject it."""
	problems = []
	if invoice.get("currency") != "IRR":
		problems.append(
			_("Only rial invoices are supported; this one is in {0}").format(invoice.get("currency"))
		)
	if not settings.get("memory_id"):
		problems.append(_("Set the tax memory ID in Iran ERP Settings"))
	seller_code = normalize_digits(seller.get("iran_economic_code") or seller.get("tax_id") or "")
	if not seller_code:
		problems.append(_("Set the company's economic code"))

	buyer_national_id = normalize_digits(buyer.get("iran_national_id") or "")
	buyer_code = normalize_digits(buyer.get("iran_economic_code") or buyer.get("tax_id") or "")
	tob = buyer_type(buyer_national_id)
	# Type 1 invoices carry the buyer's identity; without it only a type 2 invoice is possible
	invoice_type = 1 if (tob or buyer_code) else 2

	vat_rates = {
		tax.account_head: flt(tax.rate)
		for tax in invoice.get("taxes") or []
		if tax.get("charge_type") == "On Net Total" and tax.get("account_type") == "Tax"
	}

	body = []
	for item in invoice.get("items") or []:
		qty = abs(flt(item.qty))
		fee = max(flt(item.get("price_list_rate")), flt(item.rate))
		before_discount = _rial(fee * qty)
		after_discount = _rial(abs(flt(item.net_amount)))
		rate = item_vat_rate(item, vat_rates)
		vat = _rial(after_discount * rate / 100)
		sstid = item_codes.get(item.item_code)
		if not sstid:
			problems.append(
				_("Row {0}: set the 13-digit product/service ID of item {1}").format(
					item.idx, item.item_code or item.item_name
				)
			)
		unit = unit_codes.get(item.uom)
		if not unit:
			problems.append(_("Row {0}: set the Moadian unit code of unit {1}").format(item.idx, item.uom))
		body.append(
			{
				"sstid": sstid,
				"sstt": (item.item_name or "")[:400],
				"am": qty,
				"mu": unit,
				"fee": _rial(fee),
				"prdis": before_discount,
				"dis": before_discount - after_discount,
				"adis": after_discount,
				"vra": rate,
				"vam": vat,
				"odam": 0,
				"tsstam": after_discount + vat,
			}
		)

	totals = {
		"tprdis": sum(line["prdis"] for line in body),
		"tdis": sum(line["dis"] for line in body),
		"tadis": sum(line["adis"] for line in body),
		"tvam": sum(line["vam"] for line in body),
		"todam": 0,
	}
	totals["tbill"] = totals["tadis"] + totals["tvam"] + totals["todam"]
	if abs(totals["tbill"] - abs(_rial(invoice.get("rounded_total") or invoice.get("grand_total")))) > len(
		body
	):
		problems.append(
			_(
				"The computed total {0} differs from the invoice total {1}; check taxes that are not VAT"
			).format(totals["tbill"], abs(_rial(invoice.get("grand_total"))))
		)

	unpaid = min(abs(_rial(invoice.get("outstanding_amount"))), totals["tbill"])
	settlement = CASH if not unpaid else CREDIT if unpaid == totals["tbill"] else MIXED

	is_return = cint(invoice.get("is_return"))
	if is_return and not settings.get("original_tax_id"):
		problems.append(_("The invoice this return is against has no tax number yet"))

	header = {
		"taxid": settings.get("tax_id"),
		"inno": f"{cint(settings.get('serial')):010X}" if settings.get("serial") else None,
		"indatim": _ms(datetime.datetime.combine(getdate(invoice.posting_date), datetime.time(12))),
		"indati2m": _ms(invoice.get("creation") or invoice.posting_date),
		"inty": invoice_type,
		"inp": 1,
		"ins": RETURN if is_return else ORIGINAL,
		"irtaxid": settings.get("original_tax_id") if is_return else None,
		"tins": seller_code,
		"tob": tob,
		"bid": buyer_national_id or None,
		"tinb": buyer_code or None,
		"bpc": normalize_digits(buyer.get("pincode") or "") or None,
		**totals,
		"setm": settlement,
		"cap": totals["tbill"] - unpaid,
		"insp": unpaid,
		"tvop": totals["tvam"],
	}
	return {"header": header, "body": body, "payments": []}, problems


def load(invoice_name: str):
	"""Everything build_payload needs, read from the database."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice.check_permission("read")
	for tax in invoice.taxes:
		tax.account_type = frappe.get_cached_value("Account", tax.account_head, "account_type")
	seller = (
		frappe.db.get_value("Company", invoice.company, ["iran_economic_code", "tax_id"], as_dict=True) or {}
	)
	buyer = (
		frappe.db.get_value(
			"Customer", invoice.customer, ["iran_national_id", "iran_economic_code", "tax_id"], as_dict=True
		)
		or {}
	)
	if invoice.customer_address:
		buyer["pincode"] = frappe.db.get_value("Address", invoice.customer_address, "pincode")
	item_codes = {
		row.item_code: frappe.db.get_value("Item", row.item_code, "iran_sstid")
		for row in invoice.items
		if row.item_code
	}
	unit_codes = {
		row.uom: frappe.db.get_value("UOM", row.uom, "iran_moadian_unit_code") for row in invoice.items
	}
	return invoice, seller, buyer, item_codes, unit_codes


@frappe.whitelist()
def prepare(sales_invoice: str) -> dict:
	"""Give a submitted sales invoice its tax number (once) and return the Moadian invoice data."""
	invoice, seller, buyer, item_codes, unit_codes = load(sales_invoice)
	if invoice.docstatus != 1:
		frappe.throw(_("Submit the invoice first"))

	memory_id = (frappe.db.get_single_value("Iran ERP Settings", "moadian_memory_id") or "").strip().upper()
	settings = {"memory_id": memory_id}
	if invoice.is_return and invoice.return_against:
		settings["original_tax_id"] = frappe.db.get_value(
			"Sales Invoice", invoice.return_against, "iran_tax_id"
		)

	tax_id, serial = invoice.get("iran_tax_id"), invoice.get("iran_moadian_serial")
	_payload, problems = build_payload(invoice, seller, buyer, item_codes, unit_codes, settings)
	if not tax_id and not problems:
		invoice.check_permission("submit")
		from frappe.model.naming import getseries

		# One counter for all invoices of this memory, so serials never repeat
		serial = int(getseries(f"IRAN-MOADIAN-{memory_id}-", 10))
		tax_id = generate_tax_id(memory_id, getdate(invoice.posting_date), serial)
		invoice.db_set({"iran_tax_id": tax_id, "iran_moadian_serial": serial})
	settings.update(tax_id=tax_id, serial=serial)
	payload, problems = build_payload(invoice, seller, buyer, item_codes, unit_codes, settings)
	return {"tax_id": tax_id, "payload": payload, "problems": problems}
