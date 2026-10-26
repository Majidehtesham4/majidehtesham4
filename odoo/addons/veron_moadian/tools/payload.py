"""The electronic invoice of the Moadian service (سامانه مودیان) for a sales invoice, in the field names of
the tax organization's invoice pattern 1 (sale). It is built from plain values, so it is tested without a
database; the problems that would make the tax organization reject it are returned as codes."""

import datetime

from .identifiers import normalize_digits

# Invoice subject (ins)
ORIGINAL, RETURN = 1, 4
# Settlement method (setm)
CASH, CREDIT, MIXED = 1, 2, 3
TEHRAN = datetime.timezone(datetime.timedelta(hours=3, minutes=30))


def rial(value) -> int:
	return round(value or 0)


def milliseconds(value) -> int:
	if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
		value = datetime.datetime.combine(value, datetime.time(12), TEHRAN)
	elif value.tzinfo is None:
		value = value.replace(tzinfo=datetime.timezone.utc)
	return int(value.timestamp() * 1000)


def buyer_type(national_id: str):
	"""tob: 1 for a person (10-digit national code), 2 for a legal entity (11-digit national id)"""
	digits = normalize_digits(national_id or "")
	return {10: 1, 11: 2}.get(len(digits)) if digits.isdigit() else None


def build(invoice: dict, seller: dict, buyer: dict, settings: dict):
	"""(payload, problems): problems are (code, values) the caller words"""
	problems = []
	if invoice.get("currency") != "IRR":
		problems.append(("currency", {"currency": invoice.get("currency")}))
	if not settings.get("memory_id"):
		problems.append(("memory", {}))
	seller_code = normalize_digits(seller.get("economic_code") or "")
	if not seller_code:
		problems.append(("seller", {}))

	national_id = normalize_digits(buyer.get("national_id") or "")
	buyer_code = normalize_digits(buyer.get("economic_code") or "")
	tob = buyer_type(national_id) or buyer_type(buyer_code)
	# Type 1 carries the buyer; without the buyer's id only type 2 is possible
	invoice_type = 1 if (national_id or buyer_code) else 2

	body = []
	for line in invoice.get("lines") or []:
		quantity = abs(line["quantity"])
		after_discount = rial(abs(line["subtotal"]))
		discount = line.get("discount") or 0
		before_discount = rial(after_discount / (1 - discount / 100)) if discount < 100 else rial(abs(line["price_unit"]) * quantity)
		vat = rial(abs(line["total"]) - abs(line["subtotal"]))
		if not line.get("sstid"):
			problems.append(("sstid", {"row": line["row"], "product": line["name"]}))
		if not line.get("unit"):
			problems.append(("unit", {"row": line["row"], "unit": line.get("unit_name") or ""}))
		body.append({
			"sstid": line.get("sstid"),
			"sstt": (line["name"] or "")[:400],
			"am": quantity,
			"mu": line.get("unit"),
			"fee": rial(before_discount / quantity) if quantity else 0,
			"prdis": before_discount,
			"dis": before_discount - after_discount,
			"adis": after_discount,
			"vra": line.get("vat_rate") or 0,
			"vam": vat,
			"odam": 0,
			"tsstam": after_discount + vat,
		})

	totals = {
		"tprdis": sum(item["prdis"] for item in body),
		"tdis": sum(item["dis"] for item in body),
		"tadis": sum(item["adis"] for item in body),
		"tvam": sum(item["vam"] for item in body),
		"todam": 0,
	}
	totals["tbill"] = totals["tadis"] + totals["tvam"] + totals["todam"]
	if abs(totals["tbill"] - rial(abs(invoice.get("amount_total") or 0))) > len(body):
		problems.append(("total", {"computed": totals["tbill"], "total": rial(abs(invoice.get("amount_total") or 0))}))

	unpaid = min(rial(abs(invoice.get("amount_residual") or 0)), totals["tbill"])
	settlement = CASH if not unpaid else CREDIT if unpaid == totals["tbill"] else MIXED

	is_return = bool(invoice.get("is_return"))
	if is_return and not settings.get("original_tax_id"):
		problems.append(("original", {}))

	serial = settings.get("serial")
	header = {
		"taxid": settings.get("tax_id"),
		"inno": f"{int(serial):010X}" if serial else None,
		"indatim": milliseconds(invoice["invoice_date"]),
		"indati2m": milliseconds(invoice.get("create_date") or invoice["invoice_date"]),
		"inty": invoice_type,
		"inp": 1,
		"ins": RETURN if is_return else ORIGINAL,
		"irtaxid": settings.get("original_tax_id") if is_return else None,
		"tins": seller_code,
		"tob": tob,
		"bid": national_id or None,
		"tinb": buyer_code or None,
		"bpc": normalize_digits(buyer.get("zip") or "") or None,
		**totals,
		"setm": settlement,
		"cap": totals["tbill"] - unpaid,
		"insp": unpaid,
		"tvop": totals["tvam"],
	}
	return {"header": header, "body": body, "payments": []}, problems
