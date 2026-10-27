"""The fields of Iranian documents read from their text without any AI: the official sales invoice («صورتحساب
فروش کالا و خدمات») and simple invoices, card-reader and shop receipts, cheques (Sayad), purchase documents.
The text comes from the PDF itself or from the built-in OCR. What is not clear stays empty; the confidence is
«medium» only when the amounts agree with each other, and a person always checks the fields."""

import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يكۀ", "01234567890123456789یکه")
NUMBER = r"(\d{1,3}(?:[,٬،]\d{3})+|\d+)(?:[.٫/]\d+)?"
DATE = re.compile(r"\b(1[34]\d\d\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{1,2}|20\d\d-\d{1,2}-\d{1,2})\b")
BANKS = ("ملی", "ملت", "صادرات", "تجارت", "سپه", "پاسارگاد", "سامان", "پارسیان", "رسالت", "رفاه", "کشاورزی", "مسکن",
	"اقتصاد نوین", "آینده", "شهر", "دی", "سینا", "کارآفرین", "توسعه تعاون", "توسعه صادرات", "صنعت و معدن", "پست بانک",
	"قرض الحسنه مهر ایران", "خاورمیانه", "سرمایه", "گردشگری", "ایران زمین", "ملل")


def _clean(text):
	# Half-spaces and the direction marks the OCR puts around Latin letters are taken out
	return re.sub(r"[\u200e\u200f\u202a-\u202e]", "", (text or "").translate(_DIGITS).replace("\u200c", " "))


def _lines(text):
	return [re.sub(r"[ \t]+", " ", line).strip() for line in _clean(text).splitlines() if line.strip()]


def _value(raw):
	try:
		return float(re.sub(r"[,٬،]", "", raw.split(".")[0].split("٫")[0].split("/")[0]))
	except ValueError:
		return None


def _amounts(line, least=1000):
	# Dates and times are not amounts
	line = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", DATE.sub(" ", line))
	values = [_value(raw) for raw in re.findall(NUMBER, line)]
	return [v for v in values if v and v >= least]


def _amount(lines, pattern, exclude=None, least=1000):
	"""The largest amount on the first line that names it, or on the line after when the amount is printed below"""
	for index, line in enumerate(lines):
		if re.search(pattern, line, re.I) and not (exclude and re.search(exclude, line, re.I)):
			values = _amounts(line, least)
			if not values and index + 1 < len(lines):
				values = _amounts(lines[index + 1], least)
			if values:
				return max(values)
	return None


def _date(text, pattern=None):
	if pattern:
		for line in _lines(text):
			if re.search(pattern, line):
				match = DATE.search(line)
				if match:
					return re.sub(r"\s+", "", match.group(1)).replace("-", "/").replace(".", "/") \
						if match.group(1).startswith("1") else match.group(1)
	match = DATE.search(_clean(text))
	if not match:
		return ""
	value = re.sub(r"\s+", "", match.group(1))
	return value.replace("-", "/").replace(".", "/") if value.startswith("1") else value


def _after_label(line):
	"""What follows the label on a «label: value» line"""
	parts = re.split(r"[:：]", line, 1)
	return parts[1].strip(" -–") if len(parts) == 2 else ""


def _section(lines, heading, others):
	"""The lines of one part of an official invoice, e.g. from «مشخصات فروشنده» to «مشخصات خریدار»"""
	start = next((i for i, line in enumerate(lines) if re.search(heading, line)), None)
	if start is None:
		return []
	end = next((i for i, line in enumerate(lines[start + 1:], start + 1) if re.search(others, line)), len(lines))
	return lines[start:end]


def _party(lines):
	name, tax_id = "", ""
	for line in lines:
		if not name and re.search(r"نام\s*(?:شخص|شرکت|فروشگاه|فروشنده|خریدار)|نام\s*:|^نام", line):
			name = _after_label(line)
		if not tax_id:
			match = re.search(r"(?:شماره|کد|شناسه)\s*(?:اقتصادی|ملی)[^\d]{0,15}(\d{10,14})", line)
			if match:
				tax_id = match.group(1)
	return name[:120], tax_id


def _confidence(total, vat, untaxed):
	if total and untaxed and vat is not None and abs(untaxed + (vat or 0) - total) <= max(1, total * 0.002):
		return "medium"
	return "low"


def invoice(text):
	lines = _lines(text)
	clean = "\n".join(lines)
	fields = {"date": "", "invoice_number": "", "vendor": "", "vendor_tax_id": "", "buyer": "", "untaxed_amount": "",
		"vat_amount": "", "total_amount": "", "currency": "", "due_date": "", "lines": [], "confidence": "low"}
	match = re.search(r"(?:شماره\s*(?:فاکتور|صورت\s*حساب|سریال|سند)?|invoice\s*(?:no|number|#)?)\s*[:：#]?\s*"
		r"([A-Za-z0-9][A-Za-z0-9\-/]{0,30})", clean, re.I)
	if match:
		fields["invoice_number"] = match.group(1)
	fields["date"] = _date(clean, r"تاریخ(?!\s*سررسید)|date")
	fields["due_date"] = _date(clean, r"سررسید|due") if re.search(r"سررسید|due", clean, re.I) else ""
	seller = _section(lines, r"فروشنده|seller|vendor", r"خریدار|buyer|مشخصات\s*کالا|ردیف")
	buyer = _section(lines, r"خریدار|buyer", r"فروشنده|مشخصات\s*کالا|ردیف|شرح")
	name, tax_id = _party(seller)
	if not name:
		for line in seller[:3]:
			value = _after_label(line)
			if value and not re.search(r"فروشنده|seller|vendor", value, re.I):
				name = value[:120]
				break
	fields["vendor"], fields["vendor_tax_id"] = name, tax_id
	fields["buyer"] = _party(buyer)[0]
	if not fields["vendor_tax_id"]:
		match = re.search(r"(?:شماره|کد|شناسه)\s*(?:اقتصادی|ملی)[^\d]{0,15}(\d{10,14})", clean)
		fields["vendor_tax_id"] = match.group(1) if match else ""
	if not fields["vendor"]:
		# The first name on the invoice is the seller's, before the buyer's; else its first line that is not a title
		names = [_after_label(line) for line in lines if re.search(r"نام\s*(?:شخص|شرکت)", line)]
		titles = r"صورت\s*حساب|فاکتور|invoice|مشخصات"
		fields["vendor"] = (names[0] if names and names[0] != fields["buyer"] else "") or next(
			(line[:120] for line in lines if not re.search(titles, line, re.I)), "")
	# A word the OCR misread («کل» as «JS») does not hide the line: the words around it are enough
	total = _amount(lines, r"قابل\s*پرداخت|(?:جمع|مبلغ).{0,15}(?:احتساب|با\s*مالیات)|مبلغ\s*نهایی|جمع\s*نهایی|"
		r"(?<!sub)(?<!sub\s)total") or _amount(lines, r"جمع\s*کل|مبلغ\s*کل", r"قبل|بدون|پیش\s*از|تخفیف")
	vat = _amount(lines, r"ارزش\s*افزوده|مالیات|عوارض|vat|tax", r"احتساب|پس\s*از|با\s*مالیات|بدون|قبل|قابل\s*پرداخت")
	untaxed = _amount(lines, r"(?:جمع|مبلغ).*(?:قبل|بدون|پیش)\s*(?:از)?\s*مالیات|subtotal|untaxed|"
		r"(?:جمع|مبلغ)\s*کل\s*پس\s*از\s*تخفیف", r"احتساب|با\s*مالیات")
	if not total:
		values = _amounts(clean)
		total = max(values) if values else None
	if vat and total and vat >= total:
		vat = None
	# The amounts agree only when all three were read, not when one is worked out from the others
	confidence = _confidence(total, vat, untaxed)
	if total and vat and not untaxed:
		untaxed = total - vat
	if re.search(r"ریال|rial|IRR", clean, re.I):
		fields["currency"] = "IRR"
	elif re.search(r"تومان", clean):
		fields["currency"] = "تومان"
	fields.update({"total_amount": total or "", "vat_amount": vat or "", "untaxed_amount": untaxed or "",
		"confidence": confidence})
	return fields


def receipt(text):
	lines = _lines(text)
	clean = "\n".join(lines)
	amount = _amount(lines, r"مبلغ|جمع|قابل\s*پرداخت|amount|total", r"مالیات|ارزش\s*افزوده|تخفیف|موجودی|مانده", least=100)
	vat = _amount(lines, r"مالیات|ارزش\s*افزوده|vat", least=10)
	number = ""
	match = re.search(r"(?:شماره\s*(?:پیگیری|مرجع|سند|رسید|فاکتور|تراکنش)|کد\s*پیگیری|سریال|ارجاع|ref|rrn|trace)"
		r"\s*[:：#]?\s*([A-Za-z0-9\-]{3,30})", clean, re.I)
	if match:
		number = match.group(1)
	vendor = ""
	for line in lines:
		if re.search(r"نام\s*(?:فروشگاه|پذیرنده|فروشنده)|پذیرنده|فروشگاه", line):
			vendor = _after_label(line) or line
			break
	if not vendor and lines:
		vendor = lines[0]
	match = re.search(r"(?:شماره|کد|شناسه)\s*(?:اقتصادی|ملی)[^\d]{0,15}(\d{10,14})", clean)
	return {"date": _date(clean), "amount": amount or "", "currency": "IRR" if re.search(r"ریال", clean) else "",
		"vendor": vendor[:120], "receipt_number": number, "description": "", "vendor_tax_id": match.group(1) if match else "",
		"vat_amount": vat or "", "confidence": "medium" if amount and number else "low"}


def cheque(text):
	lines = _lines(text)
	clean = "\n".join(lines)
	sayad = re.search(r"(?<!\d)(\d{16})(?!\d)", re.sub(r"(?<=\d)[ \-](?=\d)", "", clean))
	serial = re.search(r"سریال\s*[:：]?\s*([0-9/\-]{4,20})", clean)
	account = re.search(r"(?:شماره\s*)?حساب\s*[:：]?\s*([0-9\-./]{6,26})", clean)
	bank = next((name for name in BANKS if re.search(r"بانک\s*" + name, clean)), "")
	branch = re.search(r"شعبه\s*[:：]?\s*([^\n:]{2,40})", clean)
	payee = ""
	for line in lines:
		if re.search(r"در\s*وجه|به\s*حواله\s*کرد|pay\s*to", line, re.I):
			payee = re.split(r"در\s*وجه|به\s*حواله\s*کرد|pay\s*to", line, 1, flags=re.I)[-1].strip(" :：-")
			break
	words = next((line for line in lines if re.search(r"(?:هزار|میلیون|میلیارد).*ریال", line)), "")
	amount = _amount(lines, r"مبلغ|(?<!س)ریال|amount", r"حروف")
	return {"sayad_id": sayad.group(1) if sayad else "", "serial": serial.group(1) if serial else "", "bank": bank,
		"branch": branch.group(1).strip() if branch else "", "account_number": account.group(1) if account else "",
		"amount": amount or "", "amount_in_words": words[:200], "due_date": _date(clean, r"تاریخ|سررسید|مورخ"),
		"payee": payee[:120], "drawer": "", "confidence": "medium" if sayad and amount else "low"}


def purchase_doc(text):
	values = invoice(text)
	return {"date": values["date"], "number": values["invoice_number"], "vendor": values["vendor"],
		"total_amount": values["total_amount"], "currency": values["currency"], "lines": [], "confidence": values["confidence"]}


def product(text):
	lines = _lines(text)
	return {"name": lines[0][:120] if lines else "", "brand": "", "model": "", "color": "", "visible_text": "\n".join(lines)[:2000],
		"description": "", "confidence": "low"}


READERS = {"invoice": invoice, "receipt": receipt, "cheque": cheque, "purchase_doc": purchase_doc, "product": product}


def fields(document_type, text):
	"""The fields of a document of that type; {} for a type without a reader or a text without content"""
	reader = READERS.get(document_type)
	if not reader or not (text or "").strip():
		return {}
	return reader(text)


def best(document_type, texts):
	"""(text, fields) of the reading whose fields agree best: amounts that add up first, then the most fields read,
	then the cleanest text"""
	from .ocr import quality

	texts = [text for text in texts if (text or "").strip()]
	if not texts:
		return "", {}
	scored = []
	for index, text in enumerate(texts):
		values = fields(document_type, text)
		filled = sum(1 for key, value in values.items() if key != "confidence" and value not in (None, "", []))
		agree = values.get("confidence") == "medium"
		scored.append(((agree, filled, quality(text), -index), text, values))
	_score, text, values = max(scored, key=lambda item: item[0])
	values = dict(values)
	# Codes, numbers and dates the readings disagree on: the value most readings give
	amounts = {"total_amount", "vat_amount", "untaxed_amount", "amount", "confidence", "lines"}
	for key in values:
		if key in amounts:
			continue
		seen = [other[key] for _s, _t, other in scored if other.get(key) not in (None, "", [])]
		if seen:
			common = max(set(seen), key=seen.count)
			if seen.count(common) > seen.count(values[key]):
				values[key] = common
	return text, values
