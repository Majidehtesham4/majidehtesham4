"""The start page («شروع کار»): today's figures, and everyday tasks as short step-by-step forms.

The forms (wizards) ask only for what a task really needs, in plain words, and then run the same
built-in command the chat runs for that task, so a draft invoice made here is the one the chat makes.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

# Field for each kind of command detail
FIELD_TYPES = {
	"customer": {"fieldtype": "Link", "options": "Customer"},
	"supplier": {"fieldtype": "Link", "options": "Supplier"},
	"item": {"fieldtype": "Link", "options": "Item"},
	"warehouse": {"fieldtype": "Link", "options": "Warehouse"},
	"bank_account": {"fieldtype": "Link", "options": "Bank Account"},
	"project": {"fieldtype": "Link", "options": "Project"},
	"employee": {"fieldtype": "Link", "options": "Employee"},
	"cash_account": {"fieldtype": "Link", "options": "Account"},
	"amount": {"fieldtype": "Currency"},
	"qty": {"fieldtype": "Float"},
	"number": {"fieldtype": "Data"},
	"percent": {"fieldtype": "Percent"},
	"date": {"fieldtype": "Date"},
	"mobile": {"fieldtype": "Data", "options": "Phone"},
	"city": {"fieldtype": "Data"},
	"name": {"fieldtype": "Data"},
	"text": {"fieldtype": "Small Text"},
	"vat": {"fieldtype": "Check"},
	"payment_mode": {"fieldtype": "Select"},
	"items": {"fieldtype": "Table"},
}

# The tasks offered as forms, with the label and hint of each detail they ask for
WIZARDS = {
	"create_sales_invoice": {
		"customer": ("مشتری", "کسی که به او می‌فروشید. اگر در فهرست نیست، اول «مشتری جدید» را بزنید."),
		"items": (
			"کالاها",
			"هر ردیف یک کالا: تعداد و قیمت هر واحد به ریال. اگر قیمت را خالی بگذارید، قیمت فروش کالا گذاشته می‌شود.",
		),
		"vat": ("مالیات بر ارزش افزوده اضافه شود", "اگر مشتری باید ارزش افزوده بپردازد تیک بزنید."),
	},
	"create_quotation": {
		"customer": ("مشتری", "پیش‌فاکتور برای چه کسی است؟"),
		"items": ("کالاها", "کالا، تعداد و قیمت پیشنهادی هر واحد."),
	},
	"receive_payment": {
		"customer": ("از کدام مشتری", "مشتری‌ای که پول را داده است."),
		"amount": ("مبلغ (ریال)", "مبلغی که دریافت شد."),
		"payment_mode": ("روش دریافت", "نقدی یا واریز به حساب بانکی."),
		"bank": ("به کدام حساب بانکی", "اگر پول به حساب بانکی واریز شده، حساب را انتخاب کنید."),
	},
	"make_payment": {
		"supplier": ("به کدام تأمین‌کننده", "کسی که به او پول داده‌اید."),
		"amount": ("مبلغ (ریال)", "مبلغی که پرداخت شد."),
		"payment_mode": ("روش پرداخت", "نقدی یا از حساب بانکی."),
		"bank": ("از کدام حساب بانکی", "اگر از حساب بانکی پرداخت کرده‌اید، حساب را انتخاب کنید."),
	},
	"create_purchase_invoice": {
		"supplier": ("تأمین‌کننده", "کسی که از او خریده‌اید."),
		"items": ("کالاها", "کالا، تعداد و قیمت خرید هر واحد به ریال."),
		"vat": ("ارزش افزوده دارد", "اگر فاکتور خرید ارزش افزوده دارد تیک بزنید."),
	},
	"create_customer": {
		"name": ("نام مشتری", "نام شخص یا شرکت."),
		"mobile": ("موبایل", "اختیاری"),
		"city": ("شهر", "اختیاری"),
	},
	"create_supplier": {
		"name": ("نام تأمین‌کننده", "نام شخص یا شرکتی که از او خرید می‌کنید."),
		"mobile": ("موبایل", "اختیاری"),
	},
	"create_item": {
		"name": ("نام کالا یا خدمت", "مثلاً «مانیتور ۲۴ اینچ» یا «خدمات نصب»."),
		"amount": ("قیمت فروش (ریال)", "اختیاری"),
	},
	"stock_receipt": {
		"items": ("کالاهای واردشده", "کالا و تعداد. قیمت اختیاری است."),
		"warehouse": ("انبار", "اگر خالی بماند انبار پیش‌فرض گذاشته می‌شود."),
	},
	"stock_issue": {
		"items": ("کالاهای خارج‌شده", "کالا و تعداد."),
		"warehouse": ("از کدام انبار", "اگر خالی بماند انبار پیش‌فرض گذاشته می‌شود."),
	},
	"register_received_cheque": {
		"customer": ("از کدام مشتری", ""),
		"amount": ("مبلغ چک (ریال)", ""),
		"date": ("تاریخ سررسید", "تاریخی که روی چک نوشته شده."),
		"number": ("شماره‌ی چک یا شناسه‌ی صیادی", "شناسه‌ی صیادی ۱۶ رقمی روی چک است."),
	},
	"register_issued_cheque": {
		"supplier": ("برای کدام تأمین‌کننده", ""),
		"amount": ("مبلغ چک (ریال)", ""),
		"date": ("تاریخ سررسید", ""),
		"number": ("شماره‌ی چک یا شناسه‌ی صیادی", ""),
		"bank": ("از کدام حساب بانکی", "حسابی که دسته‌چک مال آن است."),
	},
	"create_todo": {
		"text": ("چه کاری", "مثلاً «تماس با آقای احمدی برای تسویه»."),
		"date": ("کِی", "اختیاری"),
	},
}

PAYMENT_MODE_LABELS = {"Cash": "نقدی", "Wire Transfer": "واریز به حساب بانکی"}


def _intent(name):
	from iran_erp.commands.engine import INTENT_BY_NAME

	if name not in WIZARDS:
		frappe.throw(_("This task has no form."))
	return INTENT_BY_NAME[name]


@frappe.whitelist()
def get_wizard(intent: str) -> dict:
	"""The dialog fields for a task."""
	definition = _intent(intent)
	labels = WIZARDS[intent]
	fields = []
	for slot, slot_type, required, _question in definition.get("slots") or []:
		if slot not in labels:
			continue
		label, hint = labels[slot]
		field = {"fieldname": slot, "label": label, "description": hint, "reqd": int(bool(required))}
		field.update(FIELD_TYPES.get(slot_type, {"fieldtype": "Data"}))
		if slot_type == "payment_mode":
			field["options"] = "\n".join(PAYMENT_MODE_LABELS)
			field["default"] = "Cash"
		if slot_type == "bank_account":
			field["filters"] = {"is_company_account": 1, "disabled": 0}
			field["depends_on"] = "eval:doc.payment_mode != 'Cash'" if "payment_mode" in labels else ""
		if slot_type == "items":
			with_rate = intent not in ("stock_issue",)
			field["fields"] = [
				{
					"fieldname": "item",
					"fieldtype": "Link",
					"options": "Item",
					"label": _("Item"),
					"in_list_view": 1,
					"reqd": 1,
				},
				{
					"fieldname": "qty",
					"fieldtype": "Float",
					"label": _("Quantity"),
					"in_list_view": 1,
					"default": 1,
				},
			]
			if with_rate:
				field["fields"].append(
					{"fieldname": "rate", "fieldtype": "Currency", "label": _("Rate"), "in_list_view": 1}
				)
		fields.append(field)
	return {"title": definition["title"], "fields": fields, "payment_modes": PAYMENT_MODE_LABELS}


def _values(intent: str, raw: dict) -> dict:
	"""Dialog values in the form the command's handler reads from a chat message."""
	definition = _intent(intent)
	values = {}
	for slot, slot_type, _required, _question in definition.get("slots") or []:
		value = raw.get(slot)
		if slot_type == "vat":
			values[slot] = "yes" if int(value or 0) else "no"
			continue
		if value in (None, "", []):
			continue
		if slot_type == "items":
			lines = []
			for row in value:
				if not row.get("item"):
					continue
				lines.append(
					{
						"item": row["item"],
						"label": frappe.db.get_value("Item", row["item"], "item_name") or row["item"],
						"qty": flt(row.get("qty")) or 1,
						"rate": flt(row.get("rate")) or None,
					}
				)
			if lines:
				values[slot] = {"lines": lines, "unknown": []}
		elif slot_type in ("amount", "qty", "percent"):
			values[slot] = flt(value)
		elif slot_type == "date":
			values[slot] = str(getdate(value))
		else:
			values[slot] = value
	return values


@frappe.whitelist(methods=["POST"])
def run_wizard(intent: str, values: str | dict) -> dict:
	"""Do a task from its form, as the chat command for it does."""
	from iran_erp.commands import slots as slot_readers
	from iran_erp.commands.engine import _run

	if isinstance(values, str):
		values = json.loads(values or "{}")
	result = _run(intent, _values(intent, values), slot_readers.Message(""), False, confirmed=True)
	if result.get("state"):
		# The handler still needs something the form did not ask for
		return {"answer": result.get("answer"), "actions": result.get("actions") or [], "incomplete": True}
	return {"answer": result.get("answer"), "actions": result.get("actions") or []}


# ---------------------------------------------------------------- today's figures


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _cash_and_bank(company):
	from erpnext.accounts.utils import get_balance_on

	total = 0.0
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0, "disabled": 0},
		pluck="name",
		limit=50,
	)
	for account in accounts:
		total += flt(get_balance_on(account=account, company=company))
	return total


def _sum(doctype, field, filters):
	value = frappe.get_all(doctype, filters=filters, fields=[{"SUM": field, "as": "total"}])
	return flt(value[0].total) if value else 0.0


@frappe.whitelist()
def get_summary() -> dict:
	"""The figures at the top of the start page; each one only if the user may see it."""
	import jdatetime

	from iran_erp.inbox import get_inbox

	company = _company()
	today = getdate(nowdate())
	jtoday = jdatetime.date.fromgregorian(date=today)
	month_start = jdatetime.date(jtoday.year, jtoday.month, 1).togregorian()
	cards = []

	def card(key, label, value, route, kind="money", hint=""):
		cards.append({"key": key, "label": label, "value": value, "route": route, "kind": kind, "hint": hint})

	if frappe.has_permission("Sales Invoice", "read"):
		card(
			"sales",
			"فروش این ماه",
			_sum(
				"Sales Invoice",
				"base_net_total",
				{"company": company, "docstatus": 1, "posting_date": [">=", month_start]},
			),
			"/desk/sales-invoice?docstatus=1",
		)
		card(
			"receivable",
			"طلب از مشتری‌ها",
			_sum(
				"Sales Invoice",
				"outstanding_amount",
				{"company": company, "docstatus": 1, "outstanding_amount": [">", 0]},
			),
			"/desk/query-report/Accounts Receivable",
			hint="فاکتورهایی که هنوز پولشان نیامده",
		)
	if frappe.has_permission("Purchase Invoice", "read"):
		card(
			"payable",
			"بدهی به تأمین‌کننده‌ها",
			_sum(
				"Purchase Invoice",
				"outstanding_amount",
				{"company": company, "docstatus": 1, "outstanding_amount": [">", 0]},
			),
			"/desk/query-report/Accounts Payable",
		)
	if frappe.has_permission("GL Entry", "read"):
		card("cash", "موجودی صندوق و بانک", _cash_and_bank(company), "/desk/query-report/General Ledger")
	if frappe.has_permission("Iran Cheque", "read"):
		due = frappe.get_all(
			"Iran Cheque",
			filters={
				"company": company,
				"docstatus": 1,
				"status": ["in", ["In Hand", "Deposited", "Issued"]],
				"due_date": ["<=", add_days(today, 7)],
			},
			fields=[{"COUNT": "*", "as": "count"}],
		)
		card(
			"cheques",
			"چک‌های سررسید تا یک هفته",
			(due[0].count if due else 0),
			"/desk/iran-cheque?status=" + json.dumps(["in", ["In Hand", "Deposited", "Issued"]]),
			kind="count",
		)
	inbox = get_inbox()
	card("tasks", "کارهای منتظر من", inbox.get("total") or 0, "", kind="count")
	return {"company": company, "cards": cards, "user": frappe.utils.get_fullname(frappe.session.user)}
