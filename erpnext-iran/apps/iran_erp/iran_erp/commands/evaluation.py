"""How well the assistant understands requests: several everyday phrasings of each capability, with
what a right answer is. A case passes when the right capability answered (not a guess, not «I did
not understand», not handed to the AI model), the details expected were read (and none that were
not said), the capability's own tool ran, and the answer links to the right record, list or report.
The wording of the answer is not judged.

	bench --site frontend execute iran_erp.commands.evaluation.report

prints each case and the share that passed; tests/test_evaluation.py runs the same cases on data
made for them, and also checks the figures.
"""

import json

import frappe

# turns: what the user writes, in order (a follow-up or the answer to a question).
# intent: the capability that must give the last answer. link: text the answer's links must have.
# without_ai: also checked with an AI model at hand, the answer must come from the capability.
CASES = [
	{
		"capability": "investor_info",
		"phrasings": [
			["یک سرمایه‌گذار داریم به نام مجید احتشام، اطلاعاتشو بیار"],
			["یک سرمایه‌گذار داریم به نام مجید احتشام اطلاعاتشو بیار"],
			["اطلاعات سرمایه گذار مجید احتشام"],
			["سرمایه گذار احتشام رو نشون بده"],
			["مجید احتشام چقدر سرمایه گذاشته"],
			["وضعیت سرمایه گذاری مجید احتشام چیه"],
			["مشخصات سرمایه گذار مجید احتشام رو میخوام"],
			["از مجید احتشام سرمایه گذارمون چه خبر"],
			["اطلاعات مجید احتشام رو بیار"],
		],
		"parameters": {"investor": True, "name": None},
		"link": "/desk/iran-investor/",
		"answer_has": "مجید احتشام",
	},
	{
		"capability": "investor_info",
		"phrasings": [["سرمایه گذارها رو نشون بده"], ["لیست سرمایه گذاران"]],
		"link": "iran-investor",
	},
	{
		"capability": "last_sales_invoices",
		"phrasings": [
			["فاکتورهای فروش رو برام بیار"],
			["آخرین فاکتورهای فروش"],
			["فاکتورای فروش"],
			["فاکتور فروش هامون رو ببینم"],
			["آخرین فاکتورهایی که فروختیم"],
			["فاکتورهای فروش اخیر رو لیست کن"],
			["چه فاکتورهای فروشی زدیم"],
		],
		"link": "sales-invoice",
	},
	{
		"capability": "last_sales_invoices",
		"phrasings": [
			["فاکتورهای فروش این ماه رو نشون بده"],
			["فاکتورهای فروش هفته پیش"],
			["فاکتورهای فروش رو برام بیار", "امسال"],
		],
		"parameters": {"period": True},
		"link": "sales-invoice",
	},
	{
		"capability": "last_sales_invoices",
		"phrasings": [["فاکتورهای فروش آقای کریمی"]],
		"parameters": {"customer": True},
		"link": "sales-invoice",
	},
	{
		"capability": "car_stock",
		"phrasings": [
			["موجودی خودرو رو بهم بده"],
			["چند تا ماشین داریم"],
			["موجودی ماشین ها"],
			["چند تا خودرو تو نمایشگاه داریم"],
			["ماشینامون چیا هستن"],
			["لیست خودروهای موجود"],
			["موجودی ماشین نمایشگاه رو بگو"],
			["چه ماشینایی داریم"],
			["وضعیت خودروهای نمایشگاه"],
		],
		# The catalog's defaults: every branch and owner, cars still in the lot
		"parameters": {"branch": None},
		"link": "iran-vehicle",
	},
	{
		"capability": "car_stock",
		"phrasings": [["خودروهای امانی رو بیار"], ["خودروهای امانی نمایشگاه کدوما هستن"]],
		"parameters": {"ownership": True},
		"link": "iran-vehicle",
	},
	{
		"capability": "car_stock",
		"phrasings": [["ماشین های آماده فروش"], ["ماشینای آماده‌ی فروش داریم؟"]],
		"parameters": {"status": "Ready for Sale"},
		"link": "iran-vehicle",
	},
	{
		"capability": "receivables",
		"phrasings": [
			["حساب‌های دریافتنی رو برام گزارش کن"],
			["مطالبات از مشتری‌ها"],
			["بدهی مشتری‌ها چقدره"],
			["مشتری‌ها چقدر به ما بدهکارن"],
			["طلب ما از مشتریا چقدره"],
			["مطالبات"],
			["گزارش حسابای دریافتنی"],
			["کی ها به ما بدهکارن"],
			["بدهکارای ما کیا هستن"],
			["حساب های دریافتنی"],
		],
		"link": "Accounts%20Receivable",
	},
	{
		"capability": "party_statement",
		"phrasings": [
			["صورتحساب مشتریان رو بیار"],
			["صورتحساب مشتریان رو بیار", "همه"],
			["صورتحساب مشتری", "همه"],
			["ریز حساب همه مشتریان"],
			["صورت حساب مشتریا"],
			["صورتحساب همه مشتری ها رو بده"],
			["ریز حساب مشتری‌ها"],
			["گردش حساب مشتریان"],
		],
		# «همه»: every customer, without asking again
		"parameters": {"party": "*"},
		"link": "Customer%20Ledger%20Summary",
	},
	{
		"capability": "balance",
		"phrasings": [
			["آقای کریمی چقدر بستانکار است؟"],
			["مانده حساب آقای کریمی"],
			["آقای کریمی چقدر طلب داره"],
		],
		"parameters": {"party": True},
		"link": "General%20Ledger",
		"answer_has": "کریمی",
	},
	{
		"capability": "create_user_login",
		"phrasings": [
			["برای آقای کریمی نقش کاربری با نام کاربری و رمز تعریف کن", "حسابدار", "karimi.eval", "Karimi-1405"],
			["یک کاربر حسابدار بساز به اسم سارا نیکو نام کاربری sara.eval رمز Sara-12345"],
		],
		"link": "/desk/user/",
		"draft": True,
	},
	{
		"capability": "create_investor_login",
		"phrasings": [
			["میتونی برای یک سرمایه گذار دسترسی درست کنی بتونه با یوزر نیم و پسورد لوگین کنه", "مجید احتشام", "Ehtesham-1405", "ehtesham.eval"],
		],
		"link": "/desk/user/",
		"draft": True,
	},
	# Requests that ask for a particular result, not the whole list: the shape and the filters count
	{
		"capability": "car_aging",
		"phrasings": [
			["کدوم ماشین‌ها بیشترین زمان رو تو پارکینگ موندن؟"],
			["ماشین‌هایی که بیشترین زمان رو در نمایشگاه بودن رو لیست کن"],
			["کدوم خودروها خیلی وقته موندن"],
		],
		"parameters": {"order": "longest", "output": "top"},
		"records": (1, 10),
		"link": "Vehicles%20in%20Stock",
	},
	{
		"capability": "car_aging",
		"phrasings": [["قدیمی‌ترین ماشین که پذیرش شده کدومه؟"], ["قدیمی ترین خودروی نمایشگاه"]],
		"parameters": {"order": "longest", "output": "one"},
		# The oldest one, or the few tied with it; never the whole stock
		"records": (1, 10),
		"link": "Vehicles%20in%20Stock",
	},
	{
		"capability": "sales_by_branch",
		"phrasings": [["یک گزارش از فروش هر شعبه بده"], ["فروش به تفکیک شعبه"], ["هر شعبه چقدر فروخته"], ["فروش این ماه به تفکیک شعبه"]],
		"parameters": {"group_by": "branch"},
		"answer_has": "شعبه",
		"link": "Sales%20Register",
	},
	{
		"capability": "car_search",
		"phrasings": [["ماشین کی‌ام‌سی ۱۴۰۳ مشکی رو چک کن فروخته شده؟"], ["خودرو کی ام سی ۱۴۰۳ مشکی فروخته شده یا نه"]],
		"parameters": {"model": True, "year": "1403", "color": "مشکی"},
		# Not on record: said so, with the details, and nothing else passed off as it
		"records": (0, 0),
		"answer_has": "پیدا نشد",
	},
	{
		"capability": "car_search",
		"phrasings": [["ماشین کی ام سی K7 مشکی رو چک کن فروخته شده؟"]],
		"parameters": {"model": True, "color": "مشکی"},
		"records": (1, 1),
		"link": "/desk/iran-vehicle/",
		"answer_has": "فروخته شده",
	},
	{
		"capability": "balance",
		"phrasings": [["خانم کریمی چقدر بدهکار یا بستانکاره؟"]],
		# No «خانم کریمی» on record: only the similar name is offered, not every «خانم»
		"asks": "party",
		"options_have": "کریمی",
		"answer_has": "خانم کریمی",
	},
	{
		"capability": "report_menu",
		"phrasings": [["یک گزارش بهم بده"], ["گزارش میخوام"]],
		"asks": "area",
		"options_have": "",
	},
	{
		"capability": "sales_by_branch",
		"phrasings": [["یک گزارش بهم بده", "فروش", "فروش هر شعبه"], ["یک گزارش بهم بده", "1", "2"]],
		"parameters": {"group_by": "branch"},
		"link": "Sales%20Register",
	},
	{
		"capability": "car_stock",
		"phrasings": [["فهرست همه خودروها"], ["لیست کامل ماشین ها"]],
		"parameters": {"output": "all"},
		"records": (2, 10000),
		"link": "iran-vehicle",
	},
	# The frame decides where samples alone go wrong; follow-ups continue the previous answer
	{
		"capability": "car_stock",
		"phrasings": [["لیست ماشین‌ها رو بر اساس هر شعبه بنویس"], ["خودروها رو به تفکیک شعبه لیست کن"]],
		"parameters": {"group_by": "branch"},
		"records": (1, 10000),
		"link": "iran-vehicle",
		"answer_has": "شعبه",
	},
	# «برای ... فاکتور بزن» with a customer on record, and without: the dialog cases below
	{
		"capability": "last_sales_invoices",
		"phrasings": [["۶ فاکتور آخر"]],
		"parameters": {"limit": 6},
		"records": (1, 6),
		"link": "sales-invoice",
	},
	{
		"capability": "last_sales_invoices",
		"phrasings": [["۵ فاکتور آخر"], ["موجودی خودرو رو بهم بده", "۵ فاکتور آخر"]],
		"parameters": {"limit": 5},
		"records": (1, 5),
		"link": "sales-invoice",
	},
	{
		"capability": "party_statement",
		"phrasings": [["آقای کریمی حسابشو بیار"], ["صورتحساب آقای کریمی رو نشون بده"], ["حساب آقای کریمی رو بیار"]],
		"parameters": {"party": True},
		"link": "General%20Ledger",
		"answer_has": "کریمی",
	},
	{
		"capability": "car_aging",
		"phrasings": [
			["کدام ماشین طولانی‌ترین زمان در نمایشگاه مانده؟", "دیگه چی"],
			["کدوم ماشین‌ها بیشترین زمان رو تو پارکینگ موندن؟", "بعدی"],
		],
		# The next ones of the same ranking, none shown twice
		"continues": True,
		"records": (1, 10),
		"link": "Vehicles%20in%20Stock",
	},
	{
		"capability": "open_document",
		"phrasings": [["سند {journal_entry} را باز کن"], ["{journal_entry} رو باز کن"]],
		"parameters": {"document": True},
		"link": "/desk/journal-entry/",
		"link_has_document": True,
	},
	# Operations read from their parts, in any order, carried out step by step. «answers» replies to
	# each question by the field it asks; «never_asks» are details the first message already gave.
	{
		"capability": "create_sales_invoice",
		"phrasings": [
			["برای خانم شریفی فاکتور بزن"],
			["فاکتور فروش برای خانم شریفی ثبت کن"],
			["برای خانم شریفی یک فاکتور جدید درست کن"],
			["ما به خانم شریفی کالا فروختیم؛ فاکتور کن"],
			["خانم شریفی یه فاکتور فروش براش صادر کن"],
		],
		"fixtures": {"customers": ["خانم شریفی"]},
		"first_asks": "item",
		"answers": {"item": "{item}", "qty": "3", "rate": "5 میلیون تومان", "more": "نه", "vat": "نه", "paid": "نه"},
		"never_asks": ["customer"],
		"values": {"customer": True},
		"link": "/desk/sales-invoice/",
	},
	{
		"capability": "create_sales_invoice",
		"phrasings": [["۲ تا {item} به قیمت ۵ میلیون تومان برای خانم شریفی فاکتور کن"]],
		"fixtures": {"customers": ["خانم شریفی"]},
		# Item, quantity and price were said: none of them is asked; it was paid, all of it
		"answers": {"more": "نه", "vat": "نه", "paid": "بله", "paid_amount": "همه", "paid_to": "1"},
		"never_asks": ["customer", "item", "qty", "rate"],
		"link": "/desk/payment-entry/",
	},
	{
		"capability": "create_sales_invoice",
		"phrasings": [["برای خانم شریفزاده فاکتور بزن"]],
		"fixtures": {"absent": ["خانم شریفزاده"]},
		# Not on record: said, with registering offered; then the invoice goes on
		"first_asks": "customer",
		"first_answer_has": "ثبت نشده",
		"answers": {"customer": "ثبت خانم شریفزاده", "item": "{item}", "qty": "1", "rate": "1 میلیون تومان", "more": "نه", "vat": "نه", "paid": "نه"},
		"link": "/desk/sales-invoice/",
	},
	{
		"capability": "create_customer_login",
		"phrasings": [
			["برای خانم کاظمی کاربر با نقش مشتری تعریف کن و براش یوزرنیم و پسورد بساز و بهم اطلاع بده"],
			["یه یوزر و پسورد مشتری برای خانم کاظمی بساز"],
		],
		"fixtures": {"customers": ["خانم زهرا کاظمی:zahra.eval@example.com", "خانم مریم کاظمی"]},
		# Two customers have the name: only they are offered
		"first_asks": "customer",
		"first_options_have": "کاظمی",
		"answers": {"customer": "خانم زهرا کاظمی", "password_way": "لینک ایمیل"},
		"never_asks": ["username"],
		"link": "/desk/user/",
	},
	{
		"capability": "create_customer_login",
		"phrasings": [["کاربر پورتال با نقش مشتری برای خانم مریم کاظمی تعریف کن"]],
		"fixtures": {"customers": ["خانم زهرا کاظمی:zahra.eval@example.com", "خانم مریم کاظمی"]},
		"answers": {"username": "maryam.eval", "password_way": "رمز را می‌نویسم", "password": "Maryam-1405"},
		"never_asks": ["customer"],
		"secret": "Maryam-1405",
		"link": "/desk/user/",
	},
	{
		"capability": "create_investment_contract",
		"phrasings": [
			["مبلغ ۲ میلیارد تومان از خانم شریفی بابت سرمایه‌گذاری جدید گرفتیم ثبتش کن"],
			["سرمایه گذاری جدید خانم شریفی ۲ میلیارد تومان ثبت کن"],
		],
		"fixtures": {"absent_investors": ["خانم شریفی"]},
		"answers": {"investor": "ثبت خانم شریفی", "monthly_rate": "4", "received_to": "1"},
		"never_asks": ["amount"],
		"link": "/desk/iran-investment-contract/",
	},
	{
		"capability": "stock_balance",
		"phrasings": [["موجودی انبار رو بده"], ["موجودی کالاها"]],
		"link": "Stock",
	},
]


def _placeholders() -> dict:
	return {
		"journal_entry": frappe.db.get_value("Journal Entry", {}, "name", order_by="creation desc") or "ACC-JV-0000-00000",
		"item": frappe.db.get_value("Item", {"disabled": 0, "is_sales_item": 1, "has_variants": 0}, "item_name", order_by="creation asc") or "-",
	}


def _fill(turns: list[str]) -> list[str]:
	"""Turns that name a record of this site: «{journal_entry}» its latest journal entry, «{item}» an item."""
	if not any("{" in t for t in turns):
		return turns
	values = _placeholders()
	return [t.format(**values) for t in turns]


def _fixtures(case):
	"""The customers a case talks about, made (or taken away) inside the case's savepoint."""
	from iran_erp.commands import entities

	spec = case.get("fixtures") or {}
	for entry in spec.get("customers") or ():
		name, _sep, email = entry.partition(":")
		if not frappe.db.exists("Customer", {"customer_name": name}):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"email_id": email or None,
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
				}
			).insert(ignore_permissions=True)
	for name in spec.get("absent") or ():
		for found in frappe.get_all("Customer", filters={"customer_name": name}, pluck="name"):
			frappe.db.set_value("Customer", found, "disabled", 1)
	for name in spec.get("absent_investors") or ():
		for found in frappe.get_all("Iran Investor", filters={"full_name": name}, pluck="name"):
			frappe.db.set_value("Iran Investor", found, "full_name", f"{name} (old)")
	for kind in ("customer", "investor", "item"):
		entities.forget(kind)


def run_dialog(case, turns, ai_available=False, states=None, asked=None) -> dict:
	"""The first turns, then each question answered by the field it asks, up to MAX_TURNS."""
	from iran_erp.commands.engine import handle

	reply = run_case(turns, ai_available, states)
	values = _placeholders()
	answers = {k: v.format(**values) for k, v in (case.get("answers") or {}).items()}
	for _turn in range(MAX_TURNS):
		state = reply.get("state") or {}
		field = (state.get("operation") or {}).get("asking") or state.get("waiting")
		if not field:
			break
		if asked is not None:
			asked.append(field)
		if field not in answers:
			break
		reply = handle(answers[field], state, ai_available=ai_available)
		if states is not None:
			states.append(reply.get("state") or {})
	return reply


MAX_TURNS = 12


def run_case(turns: list[str], ai_available: bool = False, states: list | None = None) -> dict:
	from iran_erp.commands.engine import handle

	state, reply = None, {}
	for text in _fill(turns):
		reply = handle(text, state, ai_available=ai_available)
		state = reply.get("state")
		if states is not None:
			states.append(state or {})
	return reply


def check(case: dict, turns: list[str], ai_available: bool = False) -> tuple[bool, str, dict]:
	"""(passed, why not, what ran) for one phrasing."""
	frappe.db.savepoint("iran_eval")
	states, asked, first = [], [], {}
	try:
		_fixtures(case)
		if case.get("answers"):
			first = run_case(turns, ai_available)
			reply = run_dialog(case, turns, ai_available, states, asked)
		else:
			reply = run_case(turns, ai_available, states)
	except Exception as e:
		frappe.db.rollback(save_point="iran_eval")
		return False, f"error: {e}", {}
	trace = reply.get("trace") or {}
	links = " ".join(a.get("url", "") for a in reply.get("actions") or [])
	problems = []
	if reply.get("delegate"):
		problems.append("handed to the AI model")
	if reply.get("intent") not in (case["capability"], *case.get("also", ())):
		problems.append(f"intent {reply.get('intent')}")
	state = reply.get("state") or {}
	waiting = state.get("waiting") or state.get("choose") or (state.get("operation") or {}).get("asking")
	if case.get("answers"):
		# The dialog: its first question, the questions never asked, the end reached
		first_state = (first.get("state") or {}).get("operation") or first.get("state") or {}
		if case.get("first_asks") and first_state.get("asking", first_state.get("waiting")) != case["first_asks"]:
			problems.append(f"first asked {first_state.get('asking') or first_state.get('waiting')}, not {case['first_asks']}")
		labels = [label for _v, label in first_state.get("options") or []]
		if case.get("first_options_have") and (not labels or any(case["first_options_have"] not in l for l in labels)):
			problems.append(f"first options: {labels}")
		if case.get("first_answer_has") and case["first_answer_has"] not in (first.get("answer") or ""):
			problems.append(f"first answer lacks {case['first_answer_has']}")
		repeated = [f for f in case.get("never_asks") or () if f in asked]
		if repeated:
			problems.append(f"asked again: {repeated}")
		if waiting:
			problems.append(f"stopped at {waiting} (asked {asked})")
		if case.get("secret") and (case["secret"] in (reply.get("answer") or "") or case["secret"] in str(states)):
			problems.append("the password was shown or kept")
		waiting = None
	if case.get("asks"):
		# A question was right here: about that detail, offering only related answers
		if state.get("waiting") != case["asks"]:
			problems.append(f"asked {waiting or 'nothing'}, not {case['asks']}")
		labels = [label for _v, label in state.get("options") or []]
		if case.get("options_have") is not None and not labels:
			problems.append("no options offered")
		elif case.get("options_have") and any(case["options_have"] not in label for label in labels):
			problems.append(f"unrelated options: {labels}")
	elif waiting:
		problems.append(f"still asking ({waiting})")
	if case.get("link") and case["link"] not in links:
		problems.append(f"no link with {case['link']}")
	if case.get("answer_has") and case["answer_has"] not in (reply.get("answer") or ""):
		problems.append(f"answer lacks {case['answer_has']}")
	# Details read (also while a question is asked), and details that must not be read
	values = {**(state.get("values") or {}), **((state.get("operation") or {}).get("known") or {}), **(trace.get("parameters") or {})}
	for slot, expected in (case.get("values") or {}).items():
		if expected is True and values.get(slot) in (None, ""):
			problems.append(f"{slot} not read")
	for slot in case.get("not_values") or ():
		if values.get(slot) not in (None, ""):
			problems.append(f"{slot} read as {values.get(slot)}")
	# «دیگه چی»: new records, after the ones already shown, none twice
	if case.get("continues"):
		before = (states[-2] if len(states) > 1 else {}).get("shown") or []
		after = state.get("shown") or []
		if len(after) <= len(before) or len(after) != len(set(after)):
			problems.append(f"did not continue: {len(before)} shown, then {len(after)}")
	if case.get("link_has_document") and not any(
		(trace.get("parameters") or {}).get("document", "").endswith(l.rsplit("/", 1)[-1]) for l in trace.get("links") or []
	):
		problems.append("the link is not the document named")
	# The details read, and the tool that ran: the capability's own handler
	parameters = trace.get("parameters") or {}
	for slot, expected in (case.get("parameters") or {}).items():
		found = parameters.get(slot)
		if expected is True and found in (None, ""):
			problems.append(f"{slot} not read")
		elif expected is None and found not in (None, ""):
			problems.append(f"{slot} read as {found} though not said")
		elif expected not in (True, None) and found != expected:
			problems.append(f"{slot} is {found}, not {expected}")
	if not problems and trace.get("capability") not in (reply.get("intent"), None):
		problems.append(f"ran {trace.get('capability')}")
	if not problems and not case.get("asks") and not trace.get("tool"):
		problems.append("no tool in the trace")
	# How many records the answer gives: one, a few, or all, as asked
	if case.get("records") and not case.get("asks"):
		low, high = case["records"]
		got = trace.get("records")
		if got is None or not low <= got <= high:
			problems.append(f"{got} records, not {low}–{high}")
	ran = {
		"intent": reply.get("intent"),
		"understood_by": trace.get("understood_by"),
		"parameters": parameters,
		"tool": trace.get("handler"),
		"links": trace.get("links") or [],
		"records": trace.get("records"),
		"matched": trace.get("matched"),
		"asks": state.get("waiting"),
		"options": [label for _v, label in state.get("options") or []][:6],
		"answer": (reply.get("answer") or "").split("\n")[0][:120],
	}
	frappe.db.rollback(save_point="iran_eval")
	return not problems, "; ".join(problems), ran


def evaluate(ai_available: bool = False) -> dict:
	results = []
	for case in CASES:
		for turns in case["phrasings"]:
			passed, why, ran = check(case, turns, ai_available)
			results.append({"capability": case["capability"], "turns": turns, "passed": passed, "why": why, "ran": ran})
	passed = sum(1 for r in results if r["passed"])
	return {"passed": passed, "total": len(results), "results": results}


def report():
	frappe.set_user("Administrator")
	frappe.local.lang = "fa"
	for ai in (False, True):
		out = evaluate(ai)
		print(f"\n{'With' if ai else 'Without'} an AI model: {out['passed']} of {out['total']} passed")
		for r in out["results"]:
			print(("  ok   " if r["passed"] else "  FAIL ") + r["capability"].ljust(22) + " | ".join(r["turns"]), "" if r["passed"] else "→ " + r["why"])
			ran = r["ran"]
			if ran and not ai:
				print(
					"         "
					+ f"{ran['intent']} ({ran['understood_by']}) {json.dumps(ran['parameters'], ensure_ascii=False, default=str)}"
					+ f" → {ran['tool']} → {', '.join(l[:60] for l in ran['links'][:2])}"
					+ (f" | records {ran['records']} of {ran['matched']}" if ran.get("records") is not None else "")
					+ (f" | asks {ran['asks']}: {' / '.join(ran['options'])}" if ran.get("asks") else "")
				)
				print("         «" + ran["answer"] + "»")
