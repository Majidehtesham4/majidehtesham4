"""Setting the system up for a beginner («راه‌اندازی»): questions about the business, not about accounting.

Each step explains what it is for with an everyday example and links to the help panel of the part
of the system it fills. The answers set the system up (which parts are shown, whether invoices carry
VAT); customers, suppliers, items, banks and warehouses are created as each step is saved. The
balances of the start date (cash, banks, who owes what, stock, cheques in hand) are kept until the
last step, which shows what they add up to, checks them, and records them all at once:

- cash and bank balances: one opening journal entry,
- what customers owe and what is owed to suppliers: opening invoices (or, for a balance the other
  way round, an opening journal entry), so later payments can be matched to them,
- stock: an opening stock reconciliation,
- cheques not yet cleared: cheques in Iran Cheque, as if received or issued on the start date,
- and the difference of all of it, the owners' capital, moved from the temporary opening account
  to the capital account.

The state lives in the single doctype Iran Setup.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from iran_erp.demo import opening_account

PERMITTED_ROLES = ("System Manager", "Accounts Manager")

STEPS = [
	{
		"key": "business",
		"title": "کسب‌وکار شما",
		"intro": "چند سؤال ساده درباره‌ی کاری که انجام می‌دهید. از روی جواب‌ها، بخش‌هایی که لازم ندارید پنهان می‌شود و فاکتورها با یا بدون ارزش افزوده صادر می‌شوند. لازم نیست چیزی از حسابداری بدانید.",
		"example": "فروشگاه لوازم خانگی «آریا» کالا می‌فروشد، انبار دارد، از مشتری‌ها چک می‌گیرد و مشمول ارزش افزوده است. از اول مهر ۱۴۰۵ می‌خواهد با سیستم کار کند.",
		"learn": "Company",
	},
	{
		"key": "banks",
		"title": "بانک‌ها و صندوق",
		"intro": "حساب‌های بانکی شرکت و پول نقدی که در صندوق دارید. موجودی را همان‌طور که در تاریخ شروع بوده بنویسید؛ سیستم برای هر حساب بانکی یک حساب در دفاتر می‌سازد.",
		"example": "بانک ملت، حساب «جاری شرکت»، شماره‌ی ۱۲۳۴۵۶۷۸۹، موجودی ۸۵۰٬۰۰۰٬۰۰۰ ریال؛ و ۱۲٬۰۰۰٬۰۰۰ ریال پول نقد در صندوق.",
		"learn": "Bank Account",
	},
	{
		"key": "warehouses",
		"title": "انبارها",
		"intro": "جاهایی که کالا نگه می‌دارید. اگر فقط یک انبار دارید، همان «انبار اصلی» کافی است.",
		"example": "«انبار مغازه» و «انبار کرج».",
		"learn": "Warehouse",
		"needs": "stock",
	},
	{
		"key": "customers",
		"title": "مشتری‌ها و طلب‌ها",
		"intro": "کسانی که به آن‌ها می‌فروشید. اگر کسی در تاریخ شروع به شما بدهکار بوده، مبلغش را بنویسید (بدون چک‌هایی که از او گرفته‌اید و هنوز پاس نشده؛ آن‌ها را در قدم چک‌ها بنویسید). می‌توانید فهرست را از اکسل کپی کنید و اینجا بچسبانید.",
		"example": "آقای احمدی، ۰۹۱۲۱۲۳۴۵۶۷، بدهکار ۴۵٬۰۰۰٬۰۰۰ ریال. اگر مشتری از قبل پول داده و شما به او بدهکارید، مبلغ را با منفی بنویسید: −۵٬۰۰۰٬۰۰۰.",
		"learn": "Customer",
	},
	{
		"key": "suppliers",
		"title": "تأمین‌کننده‌ها و بدهی‌ها",
		"intro": "کسانی که از آن‌ها می‌خرید. اگر در تاریخ شروع به کسی بدهکار بوده‌اید، مبلغش را بنویسید (بدون چک‌هایی که به او داده‌اید و هنوز پاس نشده).",
		"example": "پخش البرز، ۰۹۳۵۱۲۳۴۵۶۷، طلبکار ۱۲۰٬۰۰۰٬۰۰۰ ریال.",
		"learn": "Supplier",
	},
	{
		"key": "items",
		"title": "کالاها و موجودی انبار",
		"intro": "کالاها یا خدماتی که می‌فروشید. برای کالاهایی که در انبار دارید، تعداد و قیمت خرید هر واحد را بنویسید تا ارزش انبار درست حساب شود. قیمت فروش اختیاری است و در فاکتورها خودکار می‌آید.",
		"example": "مانیتور ۲۴ اینچ، قیمت فروش ۱۲٬۰۰۰٬۰۰۰، قیمت خرید ۹٬۵۰۰٬۰۰۰، ۱۵ عدد در «انبار مغازه». برای خدمات مثل «نصب» فقط نام و قیمت.",
		"learn": "Item",
	},
	{
		"key": "cheques",
		"title": "چک‌های در جریان",
		"intro": "چک‌هایی که در تاریخ شروع دستتان است و هنوز وصول نشده، و چک‌هایی که داده‌اید و هنوز پاس نشده. مشتری یا تأمین‌کننده‌ی هر چک باید در قدم‌های قبل آمده باشد.",
		"example": "چک دریافتی از آقای احمدی، ۲۰٬۰۰۰٬۰۰۰ ریال، سررسید ۱۴۰۵/۰۸/۱۵، شماره‌ی ۷۷۸۸۹۹.",
		"learn": "Iran Cheque",
		"needs": "cheques",
	},
	{
		"key": "review",
		"title": "بازبینی و ثبت",
		"intro": "جمع آنچه وارد کردید را ببینید. سرمایه یعنی دارایی‌ها منهای بدهی‌ها؛ اگر عدد عجیبی می‌بینید، به قدم مربوط برگردید. با «ثبت مانده‌های اول دوره» همه‌ی سندها یک‌جا ساخته می‌شوند.",
		"example": "صندوق و بانک ۸۶۲ میلیون + طلب از مشتری‌ها ۴۵ میلیون + انبار ۱۴۲٫۵ میلیون − بدهی به تأمین‌کننده‌ها ۱۲۰ میلیون = سرمایه‌ی ۹۲۹٫۵ میلیون ریال.",
		"learn": "Journal Entry",
	},
]

# Columns of each step's table, as dialog table fields
TABLES = {
	"banks": [
		{"fieldname": "bank", "label": "نام بانک", "fieldtype": "Data", "reqd": 1},
		{"fieldname": "account_name", "label": "نام حساب", "fieldtype": "Data"},
		{"fieldname": "account_number", "label": "شماره‌ی حساب یا شبا", "fieldtype": "Data"},
		{"fieldname": "balance", "label": "موجودی (ریال)", "fieldtype": "Currency"},
	],
	"warehouses": [{"fieldname": "warehouse_name", "label": "نام انبار", "fieldtype": "Data", "reqd": 1}],
	"customers": [
		{"fieldname": "name", "label": "نام مشتری", "fieldtype": "Data", "reqd": 1},
		{"fieldname": "mobile", "label": "موبایل", "fieldtype": "Data"},
		{"fieldname": "national_id", "label": "کد/شناسه ملی", "fieldtype": "Data"},
		{"fieldname": "balance", "label": "بدهکار به ما (ریال)", "fieldtype": "Currency"},
	],
	"suppliers": [
		{"fieldname": "name", "label": "نام تأمین‌کننده", "fieldtype": "Data", "reqd": 1},
		{"fieldname": "mobile", "label": "موبایل", "fieldtype": "Data"},
		{"fieldname": "balance", "label": "ما بدهکاریم (ریال)", "fieldtype": "Currency"},
	],
	"items": [
		{"fieldname": "item_name", "label": "نام کالا یا خدمت", "fieldtype": "Data", "reqd": 1},
		{"fieldname": "selling_price", "label": "قیمت فروش", "fieldtype": "Currency"},
		{"fieldname": "cost_price", "label": "قیمت خرید هر واحد", "fieldtype": "Currency"},
		{"fieldname": "qty", "label": "تعداد در انبار", "fieldtype": "Float"},
		{"fieldname": "warehouse", "label": "انبار", "fieldtype": "Data"},
		{"fieldname": "is_service", "label": "خدمت است", "fieldtype": "Check"},
	],
	"cheques": [
		{
			"fieldname": "direction",
			"label": "نوع",
			"fieldtype": "Select",
			"options": "دریافتی\nپرداختی",
			"reqd": 1,
		},
		{"fieldname": "party", "label": "مشتری یا تأمین‌کننده", "fieldtype": "Data", "reqd": 1},
		{"fieldname": "amount", "label": "مبلغ (ریال)", "fieldtype": "Currency", "reqd": 1},
		{"fieldname": "due_date", "label": "سررسید", "fieldtype": "Date", "reqd": 1},
		{"fieldname": "number", "label": "شماره یا شناسه‌ی صیادی", "fieldtype": "Data", "reqd": 1},
	],
}

BUSINESS_TYPES = {
	"Shop": "فروشگاه",
	"Distribution": "پخش و عمده‌فروشی",
	"Manufacturing": "تولیدی",
	"Services": "خدماتی",
	"Contracting": "پیمانکاری",
	"Car Dealership": "نمایشگاه خودرو (فروش اقساطی و سرمایه‌گذار)",
}
SELLS = {"Goods": "کالا", "Services": "خدمت", "Goods and Services": "کالا و خدمت"}


# ---------------------------------------------------------------- state


def _check_permission():
	if not set(PERMITTED_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only the system manager or the accounts manager can set the system up."),
			frappe.PermissionError,
		)


def _company() -> str:
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _setup():
	return frappe.get_single("Iran Setup")


def _data(setup) -> dict:
	return json.loads(setup.data or "{}")


def _done(setup) -> list:
	return json.loads(setup.steps_done or "[]")


def _keeps_stock(setup) -> bool:
	return (setup.sells or "Goods") != "Services" and bool(setup.has_warehouse)


def _applies(step: dict, setup) -> bool:
	needs = step.get("needs")
	if needs == "stock":
		return _keeps_stock(setup)
	if needs == "cheques":
		return bool(setup.uses_cheques)
	return True


@frappe.whitelist()
def get_state() -> dict:
	_check_permission()
	setup = _setup()
	done = _done(setup)
	steps = []
	for step in STEPS:
		if not _applies(step, setup):
			continue
		steps.append(
			{**step, "done": step["key"] in done or (step["key"] == "review" and setup.opening_posted)}
		)
	return {
		"steps": steps,
		"tables": TABLES,
		"business_types": BUSINESS_TYPES,
		"business_features": _business_features(),
		"sells": SELLS,
		"answers": {
			"business_type": setup.business_type,
			"sells": setup.sells,
			"has_warehouse": setup.has_warehouse,
			"vat_registered": setup.vat_registered,
			"uses_cheques": setup.uses_cheques,
			"opening_date": str(setup.opening_date) if setup.opening_date else None,
			"branches": setup.branches,
			"parkings": setup.parkings,
			"business_features": json.loads(setup.business_features or "null"),
			"trade_name": frappe.db.get_single_value("Iran ERP Settings", "trade_name"),
			"trade_phone": frappe.db.get_single_value("Iran ERP Settings", "trade_phone"),
		},
		"data": _data(setup),
		"warehouses": frappe.get_all(
			"Warehouse", filters={"company": _company(), "is_group": 0, "disabled": 0}, pluck="warehouse_name"
		),
		"opening_posted": setup.opening_posted,
		"opening_documents": json.loads(setup.opening_documents or "[]"),
		"company": _company(),
	}


@frappe.whitelist()
def get_progress() -> dict:
	"""For the card on the Start page."""
	if not set(PERMITTED_ROLES) & set(frappe.get_roles()):
		return {}
	setup = _setup()
	done = _done(setup)
	steps = [s for s in STEPS if _applies(s, setup)]
	finished = sum(1 for s in steps if s["key"] in done) + (1 if setup.opening_posted else 0)
	finished = min(finished, len(steps))
	return {"done": finished, "total": len(steps), "finished": bool(setup.opening_posted)}


@frappe.whitelist(methods=["POST"])
def save_step(step: str, values: str | dict) -> dict:
	_check_permission()
	if isinstance(values, str):
		values = json.loads(values or "{}")
	setup = _setup()
	if setup.opening_posted and step != "business":
		frappe.throw(
			_("The opening balances are already recorded. Make further changes in the documents themselves.")
		)
	data = _data(setup)
	savers = {
		"business": _save_business,
		"banks": _save_banks,
		"warehouses": _save_warehouses,
		"customers": _save_customers,
		"suppliers": _save_suppliers,
		"items": _save_items,
		"cheques": _save_cheques,
	}
	if step not in savers:
		frappe.throw(_("Unknown step"))
	savers[step](setup, data, values)
	done = _done(setup)
	if step not in done:
		done.append(step)
	setup.steps_done = json.dumps(done)
	setup.data = json.dumps(data, ensure_ascii=False, default=str)
	setup.flags.ignore_permissions = True
	setup.save()
	return get_state()


def _rows(values, key) -> list[dict]:
	"""The table's rows without empty ones."""
	return [
		r
		for r in (values.get(key) or [])
		if any(v not in (None, "", 0) for k, v in r.items() if k not in ("idx", "name"))
	]


def _fail(errors: list[str]):
	frappe.throw("<br>".join(errors[:15]), title=_("Please fix these rows"))


# ---------------------------------------------------------------- steps


def _save_business(setup, data, values):
	for field in ("business_type", "sells", "opening_date", "branches", "parkings"):
		setup.set(field, values.get(field))
	# The name customers know, for the dashboard and the printouts
	for field in ("trade_name", "trade_phone"):
		frappe.db.set_single_value("Iran ERP Settings", field, (values.get(field) or "").strip())
	from iran_erp.business import PACKS

	pack = PACKS.get(setup.business_type) or {}
	if pack.get("features"):
		# A car dealership sells goods it does not keep in the stock module: its cars have their own file
		setup.sells, setup.has_warehouse = "Goods", 0
		chosen = values.get(_features_field(setup.business_type)) or []
		setup.business_features = json.dumps([key for key, *_rest in pack["features"] if key in chosen])
	for field in ("has_warehouse", "vat_registered", "uses_cheques"):
		setup.set(field, 1 if values.get(field) else 0)
	if setup.business_type in ("Car Dealership",):
		setup.has_warehouse = 0
	if not setup.opening_date:
		frappe.throw(_("Choose the start date."))
	_show_parts(setup)
	_apply_vat(setup, data)
	_apply_business_pack(setup)


def _show_parts(setup):
	"""Only the parts the business uses stay on the home screen."""
	from iran_erp.business import visibility

	visibility.apply(setup)


def _apply_business_pack(setup):
	"""What the kind of business needs on top of the common parts, and its branches."""
	from iran_erp.business import PACKS, apply_pack, set_branches, set_parkings

	set_branches((setup.branches or "").splitlines(), _company())
	if setup.business_type in PACKS:
		features = json.loads(setup.business_features or "null")
		apply_pack(setup.business_type, _company(), features)
		set_parkings((setup.parkings or "").splitlines())


def _business_features() -> dict:
	"""For each kind of business with choices of its own: the field and the choices."""
	from iran_erp.business import PACKS

	return {
		business_type: {"field": _features_field(business_type), "choices": pack["features"]}
		for business_type, pack in PACKS.items()
		if pack.get("features")
	}


def _features_field(business_type) -> str:
	return "features_" + frappe.scrub(business_type)


def _apply_vat(setup, data):
	"""Without VAT, invoices get no tax template by default; the templates stay for later."""
	company = _company()
	turned_off = data.setdefault("vat_templates_off", [])
	for doctype in ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template"):
		if setup.vat_registered:
			for name in [n for n in turned_off if frappe.db.exists(doctype, n)]:
				frappe.db.set_value(doctype, name, "is_default", 1)
				turned_off.remove(name)
		else:
			for name in frappe.get_all(doctype, filters={"company": company, "is_default": 1}, pluck="name"):
				frappe.db.set_value(doctype, name, "is_default", 0)
				turned_off.append(name)


def _bank_parent(company) -> str | None:
	from iran_erp.accounts.chart import get_account

	parent = get_account(company, "1103")
	if parent and frappe.db.get_value("Account", parent, "is_group"):
		return parent
	return frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name")


def _save_banks(setup, data, values):
	company = _company()
	rows = _rows(values, "banks")
	errors = [
		f"ردیف {i}: نام بانک را بنویسید." for i, r in enumerate(rows, 1) if not (r.get("bank") or "").strip()
	]
	if errors:
		_fail(errors)
	parent = _bank_parent(company)
	if rows and not parent:
		frappe.throw(_("The chart of accounts has no group for bank accounts."))
	saved = []
	for row in rows:
		bank = row["bank"].strip()
		title = (row.get("account_name") or "").strip() or "جاری"
		if not frappe.db.exists("Bank", bank):
			frappe.get_doc({"doctype": "Bank", "bank_name": bank}).insert(ignore_permissions=True)
		ledger_name = f"{bank} {title}"
		ledger = frappe.db.get_value(
			"Account", {"company": company, "account_name": ledger_name, "is_group": 0}
		)
		if not ledger:
			ledger = (
				frappe.get_doc(
					{
						"doctype": "Account",
						"account_name": ledger_name,
						"parent_account": parent,
						"company": company,
						"account_type": "Bank",
						"is_group": 0,
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		number = (row.get("account_number") or "").strip().replace(" ", "")
		bank_account = frappe.db.get_value("Bank Account", {"account": ledger})
		if not bank_account:
			doc = frappe.get_doc(
				{
					"doctype": "Bank Account",
					"account_name": title,
					"bank": bank,
					"account": ledger,
					"company": company,
					"is_company_account": 1,
				}
			)
			if number.upper().startswith("IR"):
				doc.iban = number.upper()
			elif number:
				doc.bank_account_no = number
			bank_account = doc.insert(ignore_permissions=True).name
		saved.append(
			{**row, "bank": bank, "account_name": title, "ledger": ledger, "bank_account": bank_account}
		)
	data["banks"] = saved
	data["cash_balance"] = flt(values.get("cash_balance"))
	from iran_erp.commands import entities

	entities.forget("bank_account")


def _save_warehouses(setup, data, values):
	company = _company()
	parent = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]}
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 1})
	names = []
	for row in _rows(values, "warehouses"):
		name = (row.get("warehouse_name") or "").strip()
		if not name:
			continue
		if not frappe.db.exists("Warehouse", {"company": company, "warehouse_name": name}):
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": name,
					"company": company,
					"parent_warehouse": parent,
				}
			).insert(ignore_permissions=True)
		names.append(name)
	data["warehouses"] = [{"warehouse_name": n} for n in names]
	from iran_erp.commands import entities

	entities.forget("warehouse")


def _save_customers(setup, data, values):
	from iran_erp.ai.tools import create_customer
	from iran_erp.utils.national_id import normalize_digits

	rows, errors, saved = _rows(values, "customers"), [], []
	for i, row in enumerate(rows, 1):
		name = (row.get("name") or "").strip()
		if not name:
			errors.append(f"ردیف {i}: نام مشتری را بنویسید.")
			continue
		mobile = normalize_digits(row.get("mobile") or "").strip() or None
		company_like = name.startswith(("شرکت", "موسسه", "مؤسسه", "فروشگاه", "گروه"))
		result = create_customer(
			name,
			mobile=mobile,
			customer_type="Company" if company_like else "Individual",
			national_id=(row.get("national_id") or "").strip() or None,
		)
		if result.get("error"):
			errors.append(f"ردیف {i} ({name}): شماره‌ی موبایل درست نیست؛ باید ۱۱ رقم و با ۰۹ شروع شود.")
			continue
		saved.append({**row, "name": name, "party": result.get("name") or result.get("customer")})
	if errors:
		_fail(errors)
	data["customers"] = saved
	from iran_erp.commands import entities

	entities.forget("customer")


def _save_suppliers(setup, data, values):
	from iran_erp.ai.tools import find_party
	from iran_erp.utils.national_id import normalize_digits

	group = frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups"
	rows, errors, saved = _rows(values, "suppliers"), [], []
	for i, row in enumerate(rows, 1):
		name = (row.get("name") or "").strip()
		if not name:
			errors.append(f"ردیف {i}: نام تأمین‌کننده را بنویسید.")
			continue
		mobile = normalize_digits(row.get("mobile") or "").strip()
		if mobile and not (len(mobile) == 11 and mobile.startswith("09") and mobile.isdigit()):
			errors.append(f"ردیف {i} ({name}): شماره‌ی موبایل درست نیست؛ باید ۱۱ رقم و با ۰۹ شروع شود.")
			continue
		party = find_party("Supplier", name)
		if not party or frappe.db.get_value("Supplier", party, "supplier_name") != name:
			supplier = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": name,
					"supplier_group": group,
					"supplier_type": "Company"
					if name.startswith(("شرکت", "موسسه", "مؤسسه", "پخش", "گروه"))
					else "Individual",
				}
			).insert(ignore_permissions=True)
			party = supplier.name
			if mobile:
				frappe.get_doc(
					{
						"doctype": "Contact",
						"first_name": name,
						"phone_nos": [{"phone": mobile, "is_primary_mobile_no": 1}],
						"links": [{"link_doctype": "Supplier", "link_name": party}],
					}
				).insert(ignore_permissions=True)
		saved.append({**row, "name": name, "party": party})
	if errors:
		_fail(errors)
	data["suppliers"] = saved
	from iran_erp.commands import entities

	entities.forget("supplier")


def _warehouse(company, text) -> str | None:
	text = (text or "").strip()
	if text:
		found = frappe.db.get_value(
			"Warehouse", {"company": company, "warehouse_name": text, "is_group": 0}
		) or frappe.db.get_value("Warehouse", {"company": company, "name": text, "is_group": 0})
		if found:
			return found
	return frappe.db.get_value(
		"Warehouse", {"company": company, "warehouse_name": "Stores", "is_group": 0}
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0, "disabled": 0})


def _save_items(setup, data, values):
	from iran_erp.ai.tools import _find_item, create_items

	company = _company()
	services_only = setup.sells == "Services"
	rows, errors, saved = _rows(values, "items"), [], []
	for i, row in enumerate(rows, 1):
		name = (row.get("item_name") or "").strip()
		label = f"ردیف {i} ({name})" if name else f"ردیف {i}"
		if not name:
			errors.append(f"{label}: نام را بنویسید.")
		is_service = services_only or bool(row.get("is_service"))
		if flt(row.get("qty")) and is_service:
			errors.append(f"{label}: خدمت موجودی انبار ندارد؛ تعداد را خالی بگذارید.")
		if flt(row.get("qty")) < 0:
			errors.append(f"{label}: تعداد نمی‌تواند منفی باشد.")
		if flt(row.get("qty")) and not flt(row.get("cost_price")):
			errors.append(f"{label}: برای کالایی که در انبار دارید، قیمت خرید هر واحد را بنویسید.")
		if (row.get("warehouse") or "").strip() and not _warehouse(company, row.get("warehouse")):
			errors.append(f"{label}: انبار «{row['warehouse']}» پیدا نشد.")
	if errors:
		_fail(errors)
	create_items(
		[
			{
				"item_name": r["item_name"].strip(),
				"selling_price": flt(r.get("selling_price")) or None,
				"is_service": services_only or bool(r.get("is_service")),
			}
			for r in rows
		],
		company=company,
	)
	for row in rows:
		code = _find_item(row["item_name"].strip())
		warehouse = _warehouse(company, row.get("warehouse")) if flt(row.get("qty")) else None
		saved.append({**row, "item_code": code, "warehouse_id": warehouse})
	data["items"] = saved
	from iran_erp.commands import entities

	entities.forget("item")


def _save_cheques(setup, data, values):
	from iran_erp.ai.tools import find_party

	rows, errors, saved = _rows(values, "cheques"), [], []
	banks = data.get("banks") or []
	for i, row in enumerate(rows, 1):
		received = (row.get("direction") or "دریافتی") == "دریافتی"
		party_type = "Customer" if received else "Supplier"
		name = (row.get("party") or "").strip()
		party = find_party(party_type, name) if name else None
		label = f"ردیف {i} ({name})" if name else f"ردیف {i}"
		if not party:
			errors.append(
				f"{label}: «{name}» در فهرست {'مشتری‌ها' if received else 'تأمین‌کننده‌ها'} نیست؛ اول آن را در قدم مربوط اضافه کنید."
			)
		if flt(row.get("amount")) <= 0:
			errors.append(f"{label}: مبلغ چک را بنویسید.")
		if not row.get("due_date"):
			errors.append(f"{label}: سررسید را بنویسید.")
		if not (row.get("number") or "").strip():
			errors.append(f"{label}: شماره‌ی چک را بنویسید.")
		if not received and not banks:
			errors.append(f"{label}: برای چک پرداختی، اول حساب بانکی را در قدم «بانک‌ها و صندوق» وارد کنید.")
		saved.append({**row, "party_type": party_type, "party_id": party})
	if errors:
		_fail(errors)
	data["cheques"] = saved


# ---------------------------------------------------------------- review and posting


def _cheque_totals(data) -> dict:
	totals = {}
	for row in data.get("cheques") or []:
		key = (row["party_type"], row["party_id"])
		totals[key] = totals.get(key, 0) + flt(row.get("amount"))
	return totals


@frappe.whitelist()
def get_review() -> dict:
	"""What the entered balances add up to, and what needs looking at before they are recorded."""
	_check_permission()
	setup = _setup()
	data = _data(setup)
	company = _company()
	received = sum(flt(r["amount"]) for r in data.get("cheques") or [] if r["party_type"] == "Customer")
	issued = sum(flt(r["amount"]) for r in data.get("cheques") or [] if r["party_type"] == "Supplier")
	cash = flt(data.get("cash_balance"))
	banks = sum(flt(r.get("balance")) for r in data.get("banks") or [])
	receivable = sum(flt(r.get("balance")) for r in data.get("customers") or [])
	payable = sum(flt(r.get("balance")) for r in data.get("suppliers") or [])
	stock = sum(flt(r.get("qty")) * flt(r.get("cost_price")) for r in data.get("items") or [])
	capital = cash + banks + receivable + received + stock - payable - issued
	lines = [
		("صندوق", cash, 1),
		("بانک‌ها", banks, 1),
		("طلب از مشتری‌ها", receivable, 1),
		("چک‌های دریافتی در جریان", received, 1),
		("موجودی انبار (به قیمت خرید)", stock, 1),
		("بدهی به تأمین‌کننده‌ها", payable, -1),
		("چک‌های پرداختی پاس‌نشده", issued, -1),
	]

	issues = []

	def issue(level, text, route=None):
		issues.append({"level": level, "text": text, "route": route})

	if not setup.opening_date:
		issue("error", "تاریخ شروع را در قدم «کسب‌وکار شما» انتخاب کنید.")
	if not opening_account(company):
		issue("error", "حساب «افتتاحیه موقت» در نمودار حساب‌ها نیست.", "/desk/account")
	if cash and not _cash_account(company):
		issue(
			"error",
			"حساب صندوق پیدا نشد؛ در تنظیمات شرکت «حساب نقدی پیش‌فرض» را انتخاب کنید.",
			f"/desk/company/{company}",
		)
	if not _capital_account(company):
		issue("error", "حساب «سرمایه» در نمودار حساب‌ها نیست.", "/desk/account")
	if setup.opening_date:
		from erpnext.accounts.utils import get_fiscal_year

		try:
			get_fiscal_year(setup.opening_date, company=company)
		except Exception:
			issue("info", "سال مالی تاریخ شروع هنوز تعریف نشده؛ هنگام ثبت خودکار ساخته می‌شود.")
	if capital < 0:
		issue("warning", "بدهی‌ها از دارایی‌ها بیشتر است و سرمایه منفی می‌شود. مبلغ‌ها را دوباره نگاه کنید.")
	no_price = [r["item_name"] for r in data.get("items") or [] if not flt(r.get("selling_price"))]
	if no_price:
		issue(
			"warning",
			f"این کالاها قیمت فروش ندارند و در فاکتور باید دستی قیمت بخورند: {'، '.join(no_price[:8])}",
			"/desk/item-price",
		)
	no_mobile = [r["name"] for r in data.get("customers") or [] if not r.get("mobile")]
	if no_mobile:
		issue(
			"info",
			f"{len(no_mobile)} مشتری شماره‌ی موبایل ندارد؛ برای پیامک و پیگیری بهتر است اضافه شود.",
			"/desk/customer",
		)
	if not data.get("banks") and not cash:
		issue("warning", "هیچ موجودی صندوق یا بانکی وارد نشده است.")
	return {
		"lines": [
			{"label": label, "amount": amount, "sign": sign} for label, amount, sign in lines if amount
		],
		"capital": capital,
		"issues": issues,
		"can_post": not setup.opening_posted and not any(i["level"] == "error" for i in issues),
		"opening_posted": setup.opening_posted,
		"opening_documents": json.loads(setup.opening_documents or "[]"),
	}


def _cash_account(company) -> str | None:
	from iran_erp.accounts.chart import get_account

	return frappe.get_cached_value("Company", company, "default_cash_account") or get_account(company, "1101")


def _capital_account(company) -> str | None:
	from iran_erp.accounts.chart import get_account

	return get_account(company, "5101") or frappe.db.get_value(
		"Account", {"company": company, "root_type": "Equity", "is_group": 0, "disabled": 0}
	)


def _ensure_fiscal_year(date, company):
	from erpnext.accounts.utils import get_fiscal_year

	try:
		get_fiscal_year(date, company=company)
	except Exception:
		import jdatetime

		from iran_erp.api import create_jalali_fiscal_year

		frappe.clear_last_message()
		create_jalali_fiscal_year(jdatetime.date.fromgregorian(date=getdate(date)).year, company)


def _journal(company, date, rows, remark) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Opening Entry",
			"is_opening": "Yes",
			"company": company,
			"posting_date": date,
			"user_remark": remark,
			"accounts": rows,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def _opening_invoice(company, date, party_type, party, amount) -> tuple[str, str]:
	from erpnext.stock.utils import get_default_stock_uom

	doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
	account_field = "income_account" if party_type == "Customer" else "expense_account"
	doc = frappe.get_doc(
		{
			"doctype": doctype,
			"company": company,
			frappe.scrub(party_type): party,
			"posting_date": date,
			"due_date": date,
			"set_posting_time": 1,
			"is_opening": "Yes",
			"update_stock": 0,
			"disable_rounded_total": 1,
			"items": [
				{
					"item_name": "مانده‌ی اول دوره",
					"description": "مانده‌ی اول دوره",
					"uom": get_default_stock_uom(),
					"qty": 1,
					"rate": amount,
					"conversion_factor": 1,
					account_field: opening_account(company),
					"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
				}
			],
		}
	)
	doc.flags.ignore_mandatory = True
	doc.flags.dont_auto_add_taxes = True
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doctype, doc.name


@frappe.whitelist(methods=["POST"])
def post_opening() -> dict:
	"""Record all the opening balances at once; nothing is recorded if any part fails."""
	_check_permission()
	setup = _setup()
	if setup.opening_posted:
		frappe.throw(_("The opening balances are already recorded."))
	review = get_review()
	if not review["can_post"]:
		frappe.throw(_("Fix the problems marked in red first."))
	company = _company()
	data = _data(setup)
	date = str(setup.opening_date)
	temp = opening_account(company)
	made = []
	try:
		_ensure_fiscal_year(date, company)

		# Cash and banks
		rows = []
		if flt(data.get("cash_balance")):
			rows.append(_signed_row(_cash_account(company), flt(data["cash_balance"])))
		for bank in data.get("banks") or []:
			if flt(bank.get("balance")):
				rows.append(_signed_row(bank["ledger"], flt(bank["balance"])))
		if rows:
			total = sum(
				flt(r.get("debit_in_account_currency")) - flt(r.get("credit_in_account_currency"))
				for r in rows
			)
			rows.append(_signed_row(temp, -total))
			made.append(("Journal Entry", _journal(company, date, rows, "موجودی اول دوره‌ی صندوق و بانک‌ها")))

		# Customers and suppliers; their uncleared cheques are added, since registering each cheque
		# below moves its amount from the party to the cheques account
		cheques = _cheque_totals(data)
		party_rows = []
		for party_type, key, sign in (("Customer", "customers", 1), ("Supplier", "suppliers", -1)):
			from erpnext.accounts.party import get_party_account

			for row in data.get(key) or []:
				amount = flt(row.get("balance")) + cheques.pop((party_type, row["party"]), 0)
				if amount > 0:
					made.append(_opening_invoice(company, date, party_type, row["party"], amount))
				elif amount < 0:
					account = get_party_account(party_type, row["party"], company)
					party_rows.append(
						{
							**_signed_row(account, amount * sign),
							"party_type": party_type,
							"party": row["party"],
							"is_advance": "Yes",
						}
					)
		# Cheques of parties not in the lists above still need their balance
		for (party_type, party), amount in cheques.items():
			if party:
				made.append(_opening_invoice(company, date, party_type, party, amount))
		if party_rows:
			total = sum(
				flt(r.get("debit_in_account_currency")) - flt(r.get("credit_in_account_currency"))
				for r in party_rows
			)
			party_rows.append(_signed_row(temp, -total))
			made.append(
				("Journal Entry", _journal(company, date, party_rows, "پیش‌دریافت‌ها و پیش‌پرداخت‌های اول دوره"))
			)

		# Stock
		stock = [r for r in data.get("items") or [] if flt(r.get("qty")) > 0 and r.get("item_code")]
		if stock:
			doc = frappe.get_doc(
				{
					"doctype": "Stock Reconciliation",
					"purpose": "Opening Stock",
					"company": company,
					"posting_date": date,
					"set_posting_time": 1,
					"expense_account": temp,
					"items": [
						{
							"item_code": r["item_code"],
							"warehouse": r.get("warehouse_id") or _warehouse(company, r.get("warehouse")),
							"qty": flt(r["qty"]),
							"valuation_rate": flt(r["cost_price"]),
						}
						for r in stock
					],
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			made.append(("Stock Reconciliation", doc.name))

		# Cheques
		bank_ledger = (data.get("banks") or [{}])[0].get("ledger")
		for row in data.get("cheques") or []:
			number = (row.get("number") or "").strip()
			cheque = frappe.get_doc(
				{
					"doctype": "Iran Cheque",
					"cheque_type": "Received" if row["party_type"] == "Customer" else "Issued",
					"company": company,
					"party_type": row["party_type"],
					"party": row["party_id"],
					"cheque_number": number,
					"sayad_id": number if len(number) == 16 and number.isdigit() else None,
					"amount": flt(row["amount"]),
					"posting_date": date,
					"due_date": row["due_date"],
					"bank_account": bank_ledger if row["party_type"] == "Supplier" else None,
					"remarks": "چک در جریان اول دوره",
				}
			)
			cheque.flags.ignore_permissions = True
			cheque.insert()
			cheque.submit()
			made.append(("Iran Cheque", cheque.name))

		# What is left in the temporary opening account is the owners' capital
		from erpnext.accounts.utils import get_balance_on

		left = flt(get_balance_on(account=temp, date=date, company=company))
		if left:
			made.append(
				(
					"Journal Entry",
					_journal(
						company,
						date,
						[_signed_row(temp, -left), _signed_row(_capital_account(company), left)],
						"سرمایه‌ی اول دوره (دارایی‌ها منهای بدهی‌ها)",
					),
				)
			)
	except Exception as e:
		frappe.db.rollback()
		frappe.clear_last_message()
		frappe.log_error(title="Iran setup: opening balances failed")
		message = frappe.utils.strip_html(str(e)) or e.__class__.__name__
		frappe.throw(_("Nothing was recorded. {0}").format(message))

	setup.reload()
	setup.opening_posted = 1
	setup.opening_documents = json.dumps([{"doctype": d, "name": n} for d, n in made], ensure_ascii=False)
	setup.flags.ignore_permissions = True
	setup.save()
	frappe.db.commit()
	return get_review()


def _signed_row(account, amount) -> dict:
	"""A journal row: a positive amount is a debit, a negative one a credit."""
	if amount >= 0:
		return {"account": account, "debit_in_account_currency": amount}
	return {"account": account, "credit_in_account_currency": -amount}
