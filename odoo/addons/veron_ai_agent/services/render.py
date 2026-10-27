"""The answers of the built-in assistant, written from a tool's output without a language model: a sentence
for the tools people ask most, and lists and tables of the rest with Persian labels."""

import re

from markupsafe import Markup, escape

from odoo.addons.veron_core.models import jalali

ISO_DATE = re.compile(r"\b(20\d\d|19\d\d)-(\d\d)-(\d\d)\b")
# Keys that are for the program, not for people
HIDDEN = {"status", "note", "currency", "model", "id", "draft_id", "source_id", "run", "task_id"}

LABELS = {
	"period": "دوره", "orders": "سفارش", "untaxed": "مبلغ بدون مالیات", "total": "جمع", "count": "تعداد",
	"customer": "مشتری", "customers": "مشتری‌ها", "vendor": "فروشنده", "salesperson": "فروشنده", "amount": "مبلغ",
	"amount_due": "مانده", "invoices": "فاکتورها", "invoice": "فاکتور", "bill": "فاکتور خرید", "bills": "فاکتورهای خرید",
	"due": "سررسید", "overdue": "سررسید گذشته", "oldest_days": "قدیمی‌ترین (روز)", "total_due": "جمع مانده",
	"date": "تاریخ", "journal": "دفتر", "journals": "دفترها", "balance": "مانده", "account": "حساب", "by_account": "به تفکیک حساب",
	"petty_cash": "تنخواه‌ها", "fund": "تنخواه", "custodian": "تنخواه‌دار", "lines": "ردیف‌ها", "label": "شرح",
	"partner": "طرف حساب", "suggestions": "پیشنهادها", "document": "سند", "items": "موارد", "check": "مورد",
	"ok": "درست است", "month": "ماه", "taxes": "مالیات‌ها", "tax": "مالیات", "tax_amount": "مبلغ مالیات", "base": "مبنا",
	"product": "کالا", "products": "کالاها", "quantity": "مقدار", "price": "قیمت", "warehouse": "انبار", "employee": "کارمند",
	"missing": "کمبود", "records": "رکوردها", "name": "نام", "state": "وضعیت", "quotations": "پیش‌فاکتورها",
	"quotation": "پیش‌فاکتور", "valid_until": "اعتبار تا", "expired": "منقضی", "biggest": "بزرگ‌ترین‌ها",
	"by_salesperson": "به تفکیک فروشنده", "groups": "گروه‌ها", "draft": "پیش‌نویس", "draft_id": "شماره‌ی پیش‌نویس",
	"posted": "ثبت قطعی", "result": "نتیجه", "results": "نتیجه‌ها", "title": "عنوان", "url": "نشانی", "text": "متن",
	"note": "یادداشت", "changes": "تغییرها", "receipts": "رسیدها", "closing": "صورت تنخواه", "sheet": "برگه",
	"columns": "ستون‌ها", "rows": "ردیف‌ها", "created": "ساخته‌شده", "skipped": "ردشده", "phone": "تلفن", "email": "ایمیل",
	"city": "شهر", "open_invoices": "فاکتورهای باز", "open_amount": "مانده‌ی باز", "last_messages": "آخرین پیام‌ها",
	"by": "توسط", "planned": "برنامه", "actual": "عملکرد", "difference": "اختلاف", "asset": "دارایی", "value": "ارزش",
	"type": "نوع", "below_minimum": "زیر حداقل", "negative": "موجودی منفی", "slow": "بدون گردش", "on_hand": "موجودی",
	"minimum": "حداقل", "to_check": "برای بررسی", "number": "شماره", "read_by": "خوانده با", "file": "فایل",
	"first_rows": "ردیف‌های اول", "totals": "جمع ستون‌ها", "sheets": "برگه‌ها", "names": "نام‌ها",
	"already_there": "از قبل موجود", "computed": "محاسبه‌شده", "problems": "مشکل‌ها", "to_complete": "برای تکمیل",
	"order": "سفارش", "employees": "کارکنان", "ready": "آماده", "payslips": "فیش‌ها", "funds": "تنخواه‌ها", "period_days": "روزها",
}


def shamsi(text):
	"""ISO dates in a text written in Shamsi"""
	def one(match):
		try:
			from datetime import date

			year, month, day = jalali.to_jalali(date(*(int(g) for g in match.groups())))
			return f"{year}/{month:02d}/{day:02d}"
		except ValueError:
			return match.group(0)

	return ISO_DATE.sub(one, text)


def _empty(value):
	if isinstance(value, dict):
		# A count of nothing found is empty too
		return all(_empty(v) for k, v in value.items() if k not in HIDDEN and not (k == "count" and not v))
	if isinstance(value, list):
		return not value
	return value in (None, "")
STATUS = {
	"denied": "این کار برای شما یا این دستیار مجاز نیست: {reason}",
	"waiting_approval": "درخواست «{summary}» ثبت شد و منتظر تأیید است ({approval}).",
	"suggested": "این را پیشنهاد کردم و چیزی تغییر نکرد: {summary} ({approval}).",
	"needs_info": "{question}",
	"failed": "انجام نشد: {error}",
	"invalid": "ورودی درست نبود: {error}",
}


def number(value):
	if isinstance(value, bool):
		return "بله" if value else "خیر"
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	if isinstance(value, int):
		return f"{value:,}"
	if isinstance(value, float):
		return f"{value:,.2f}"
	return str(value)


def label(key):
	return LABELS.get(key, key.replace("_", " "))


def value_html(value, depth=0):
	if isinstance(value, dict):
		return Markup("<ul>%s</ul>") % Markup("").join(
			Markup("<li><b>%s:</b> %s</li>") % (label(k), value_html(v, depth + 1)) for k, v in value.items()
			if v not in (None, "", [], {}) and k not in HIDDEN)
	if isinstance(value, list):
		if value and all(isinstance(item, dict) for item in value) and depth < 3:
			keys = list(dict.fromkeys(k for item in value[:50] for k in item if k not in HIDDEN))[:7]
			head = Markup("").join(Markup("<th>%s</th>") % label(k) for k in keys)
			rows = Markup("").join(Markup("<tr>%s</tr>") % Markup("").join(
				Markup("<td>%s</td>") % (value_html(item.get(k), depth + 1) if item.get(k) not in (None, "") else "")
				for k in keys) for item in value[:50])
			more = Markup("<p class='text-muted small'>%s</p>") % f"و {len(value) - 50} مورد دیگر" if len(value) > 50 else ""
			return Markup("<table class='table table-sm'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>%s") % (
				head, rows, more)
		return escape("، ".join(number(item) if not isinstance(item, (dict, list)) else str(item) for item in value[:30]))
	if value is None:
		return ""
	return escape(shamsi(number(value)))


def _sales(o):
	return f"فروش {o.get('period', '')}: {number(o.get('orders', 0))} سفارش، جمع بدون مالیات {number(o.get('untaxed', 0))}."


def _overdue(o):
	return f"{number(o.get('invoices', 0))} فاکتور سررسیدگذشته، جمع مانده {number(o.get('total_due', 0))} {o.get('currency', '')}."


def _cash(o):
	return f"جمع مانده‌ی بانک‌ها، صندوق‌ها و تنخواه‌ها: {number(o.get('total', 0))} {o.get('currency', '')}."


def _expense(o):
	return f"هزینه‌های {o.get('period', '')}: جمع {number(o.get('total', 0))} {o.get('currency', '')}."


def _draft(o):
	return f"پیش‌نویس {o.get('draft', '')} ساخته شد (جمع {number(o.get('total', 0))}). هنوز ثبت قطعی نشده است."


def _records(o):
	return f"{number(o.get('count', 0))} مورد پیدا شد." if o.get("count") else ""


HEADLINES = {
	"sales_summary": _sales, "receivables_overdue": _overdue, "cash_position": _cash, "expense_summary": _expense,
	"invoice_draft_create": _draft, "bill_from_document": _draft, "records_search": _records,
}


def answer(code, output):
	"""The answer of a tool's output, as HTML"""
	status = output.get("status") if isinstance(output, dict) else None
	if status in STATUS:
		values = {key: output.get(key, "") for key in ("reason", "summary", "approval", "question", "error")}
		return Markup("<p>%s</p>") % shamsi(STATUS[status].format(**values))
	headline = HEADLINES.get(code)
	parts = []
	if headline:
		try:
			line = headline(output)
			if line:
				parts.append(Markup("<p>%s</p>") % shamsi(line))
		except (TypeError, ValueError):
			pass
	if _empty(output):
		parts.append(Markup("<p>%s</p>") % "موردی پیدا نشد.")
	else:
		parts.append(value_html(output))
	if isinstance(output, dict) and output.get("note"):
		parts.append(Markup("<p class='text-muted small'>%s</p>") % output["note"])
	return Markup("").join(parts)
