import frappe
from frappe import _
from frappe.utils import flt, getdate

from iran_erp.commands.handlers import company, document_list, jdate, link, money, number, require
from iran_erp.utils.jalali import format_jalali

WEEKDAYS = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه")


def greet(context):
	name = frappe.utils.get_fullname(frappe.session.user)
	return _("Hello {0}! How can I help? Write «help» to see what I can do.").format(name)


def thanks(context):
	return _("You're welcome! Anything else?")


def help(context):
	from iran_erp.commands.engine import describe

	groups = {}
	for row in describe():
		groups.setdefault(row["group"], []).append(row)
	lines = [_("These are the things I can do without an AI model. Write them in your own words:")]
	for group, rows in groups.items():
		lines.append(f"\n**{group}**")
		for row in rows:
			example = row["example"].replace("{", "«").replace("}", "»")
			lines.append(f"- {row['title']} — «{example}»")
	from iran_erp.commands.howto import HOWTO

	lines.append(f"\n**{_('Questions I can answer: «how do I …»')}**")
	lines += [f"- {entry['title']} — «{entry['questions'][0]}»" for entry in HOWTO]
	return "\n".join(lines)


def my_tasks(context):
	from iran_erp.inbox import get_inbox

	inbox = get_inbox()
	if not inbox["items"]:
		return _("Nothing is waiting for you.")
	from iran_erp.commands.handlers import list_url

	lines = [f"**{_('My Tasks')}** ({number(inbox['total'])})", ""]
	actions = []
	for item in inbox["items"]:
		url = list_url(item["doctype"], item["filters"])
		lines.append(f"- [{item['label']}]({url}): {number(item['count'])}")
	return {"answer": "\n".join(lines), "actions": actions}


def today(context):
	date = getdate()
	jdate_long = format_jalali(date, "long")
	return _("Today is {0} {1} ({2}).").format(
		WEEKDAYS[date.weekday()], jdate_long, date.strftime("%Y-%m-%d")
	)


def convert_date(context):
	date = getdate(context.get("date"))
	return _("{0}: {1} in the Jalali calendar, {2} in the Gregorian calendar.").format(
		WEEKDAYS[date.weekday()], format_jalali(date, "long"), date.strftime("%Y-%m-%d")
	)


_ONES = ("", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه")
_TEENS = ("ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده")
_TENS = ("", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود")
_HUNDREDS = ("", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد")
_SCALES = ("", "هزار", "میلیون", "میلیارد", "هزار میلیارد")


def _three_digits(n: int) -> str:
	parts = []
	if n >= 100:
		parts.append(_HUNDREDS[n // 100])
		n %= 100
	if 10 <= n < 20:
		parts.append(_TEENS[n - 10])
	else:
		if n >= 20:
			parts.append(_TENS[n // 10])
			n %= 10
		if n:
			parts.append(_ONES[n])
	return " و ".join(parts)


def persian_words(value: int) -> str:
	"""12500000 -> دوازده میلیون و پانصد هزار"""
	value = int(value)
	if value == 0:
		return "صفر"
	parts, scale = [], 0
	while value and scale < len(_SCALES):
		chunk = value % 1000
		if chunk:
			parts.append(f"{_three_digits(chunk)} {_SCALES[scale]}".strip())
		value //= 1000
		scale += 1
	return " و ".join(reversed(parts))


def number_to_words(context):
	value = flt(context.get("amount"))
	words = persian_words(value)
	answer = f"{number(value)}: **{words}**"
	if value >= 10 and int(value) % 10 == 0:
		answer += "\n\n" + _("In tomans: {0} toman").format(persian_words(value // 10))
	return answer


def vat_calc(context):
	from iran_erp.accounts.chart import vat_rate_setting

	amount = flt(context.get("amount"))
	rate = flt(vat_rate_setting())
	words = context.message.words
	if any(w in ("جدا", "بدون", "خالص") for w in words):
		net = amount / (1 + rate / 100)
		return _("{0} includes {1}% VAT: before tax {2}, VAT {3}.").format(
			money(amount), number(rate), money(net), money(amount - net)
		)
	vat = amount * rate / 100
	return _("VAT at {0}% on {1} is {2}; total with VAT {3}.").format(
		number(rate), money(amount), money(vat), money(amount + vat)
	)


def employees(context):
	require("Employee")
	employee = context.get("employee")
	if employee:
		row = frappe.db.get_value(
			"Employee",
			employee,
			[
				"employee_name",
				"designation",
				"department",
				"cell_number",
				"personal_email",
				"company_email",
				"date_of_joining",
				"status",
			],
			as_dict=True,
		)
		lines = [f"**{row.employee_name}**"]
		for label, value in (
			(_("Designation"), row.designation),
			(_("Department"), row.department),
			(_("Mobile"), row.cell_number),
			(_("Email"), row.company_email or row.personal_email),
			(_("Date of Joining"), jdate(row.date_of_joining)),
			(_("Status"), _(row.status or "")),
		):
			if value:
				lines.append(f"- {label}: {value}")
		from iran_erp.ai.tools import get_url_to_form

		return {
			"answer": "\n".join(lines),
			"actions": [link(_("Open"), get_url_to_form("Employee", employee))],
		}
	return document_list(
		"Employee",
		{"status": "Active", "company": company()},
		[
			("employee_name", _("Name"), ""),
			("designation", _("Designation"), ""),
			("cell_number", _("Mobile"), ""),
		],
		_("Active employees"),
		order_by="employee_name asc",
		limit=20,
	)


def explain_page(context):
	"""The «آموزش» guide of a document type or report, in the chat."""
	from iran_erp.commands.engine import NeedSlot
	from iran_erp.help import get_guide

	doctype, report = context.get("doctype"), context.get("report")
	if not doctype and not report:
		raise NeedSlot("doctype", _("Which part? For example: «آموزش فاکتور فروش»."))
	guide = get_guide("report", report) if report and not doctype else get_guide("doctype", doctype)
	title = _(report or doctype)
	lines = [f"**{title}**", "", guide.get("about") or _("No guide has been written for this part yet.")]
	if guide.get("steps"):
		lines += ["", "**" + _("Steps") + "**"]
		lines += [f"{i}. {step}" for i, step in enumerate(guide["steps"], 1)]
	if guide.get("fields"):
		lines += ["", "**" + _("Important fields") + "**"]
		meta = frappe.get_meta(doctype) if doctype else None
		for fieldname, text in list(guide["fields"].items())[:10]:
			label = _(meta.get_label(fieldname)) if meta and meta.has_field(fieldname) else fieldname
			lines.append(f"- {label}: {text}")
	if guide.get("after"):
		lines += ["", "**پس از «ثبت نهایی» چه می‌شود؟**", guide["after"]]
	if guide.get("mistakes"):
		lines += ["", "**اشتباه‌های رایج**"] + [f"- {text}" for text in guide["mistakes"]]
	if guide.get("example"):
		lines += ["", f"**{_('Example')}:** {guide['example']}"]
	lines += [
		"",
		_("Every page also has a «Help» button at the top that explains each of its fields.")
		+ " "
		+ "«تور قدم‌به‌قدم» همان‌جا بخش‌های صفحه را یکی‌یکی نشان می‌دهد.",
	]
	return "\n".join(lines)
