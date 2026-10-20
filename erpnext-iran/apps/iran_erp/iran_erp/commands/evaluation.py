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
	{
		"capability": "stock_balance",
		"phrasings": [["موجودی انبار رو بده"], ["موجودی کالاها"]],
		"link": "Stock",
	},
]


def run_case(turns: list[str], ai_available: bool = False) -> dict:
	from iran_erp.commands.engine import handle

	state, reply = None, {}
	for text in turns:
		reply = handle(text, state, ai_available=ai_available)
		state = reply.get("state")
	return reply


def check(case: dict, turns: list[str], ai_available: bool = False) -> tuple[bool, str, dict]:
	"""(passed, why not, what ran) for one phrasing."""
	frappe.db.savepoint("iran_eval")
	try:
		reply = run_case(turns, ai_available)
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
	waiting = (reply.get("state") or {}).get("waiting") or (reply.get("state") or {}).get("choose")
	if waiting:
		problems.append(f"still asking ({waiting})")
	if case.get("link") and case["link"] not in links:
		problems.append(f"no link with {case['link']}")
	if case.get("answer_has") and case["answer_has"] not in (reply.get("answer") or ""):
		problems.append(f"answer lacks {case['answer_has']}")
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
	if not problems and not trace.get("tool"):
		problems.append("no tool in the trace")
	ran = {
		"intent": reply.get("intent"),
		"understood_by": trace.get("understood_by"),
		"parameters": parameters,
		"tool": trace.get("handler"),
		"links": trace.get("links") or [],
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
				)
				print("         «" + ran["answer"] + "»")
