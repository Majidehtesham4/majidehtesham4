"""How well the assistant understands requests: several everyday phrasings of each capability, with
what a right answer is. A case passes when the right capability answered (not a guess, not «I did
not understand», not handed to the AI model), the details were read, and the answer links to the
right record, list or report. The wording of the answer is not judged.

	bench --site frontend execute iran_erp.commands.evaluation.report

prints each case and the share that passed; tests/test_evaluation.py runs the same cases on data
made for them, and also checks the figures.
"""

import frappe

# turns: what the user writes, in order (a follow-up or the answer to a question).
# intent: the capability that must give the last answer. link: text the answer's links must have.
# without_ai: also checked with an AI model at hand, the answer must come from the capability.
CASES = [
	{
		"capability": "investor_info",
		"phrasings": [
			["یک سرمایه‌گذار داریم به نام مجید احتشام، اطلاعاتشو بیار"],
			["اطلاعات سرمایه گذار مجید احتشام"],
			["سرمایه گذار احتشام رو نشون بده"],
			["مجید احتشام چقدر سرمایه گذاشته"],
			["وضعیت سرمایه گذاری مجید احتشام چیه"],
		],
		"link": "/desk/iran-investor/",
		"answer_has": "مجید احتشام",
	},
	{
		"capability": "last_sales_invoices",
		"phrasings": [
			["فاکتورهای فروش رو برام بیار"],
			["آخرین فاکتورهای فروش"],
			["فاکتورهای فروش این ماه رو نشون بده"],
			["فاکتورهای فروش رو برام بیار", "امسال"],
		],
		"link": "sales-invoice",
	},
	{
		"capability": "car_stock",
		"phrasings": [
			["موجودی خودرو رو بهم بده"],
			["چند تا ماشین داریم"],
			["خودروهای امانی رو بیار"],
			["ماشین های آماده فروش"],
			["موجودی ماشین ها"],
		],
		"link": "iran-vehicle",
	},
	{
		"capability": "receivables",
		"phrasings": [
			["حساب‌های دریافتنی رو برام گزارش کن"],
			["مطالبات از مشتری‌ها"],
			["بدهی مشتری‌ها چقدره"],
			["مشتری‌ها چقدر به ما بدهکارن"],
		],
		"link": "Accounts%20Receivable",
		# «بدهی مشتری‌ها» reads like a balance; for everyone it answers with the receivables
		"also": ["balance"],
	},
	{
		"capability": "party_statement",
		"phrasings": [
			["صورتحساب مشتریان رو بیار"],
			["صورتحساب مشتریان رو بیار", "همه"],
			["صورتحساب مشتری", "همه"],
			["ریز حساب همه مشتریان"],
		],
		"link": "Customer%20Ledger%20Summary",
	},
	{
		"capability": "balance",
		"phrasings": [
			["آقای کریمی چقدر بستانکار است؟"],
			["مانده حساب آقای کریمی"],
			["آقای کریمی چقدر طلب داره"],
		],
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


def check(case: dict, turns: list[str], ai_available: bool = False) -> tuple[bool, str]:
	"""(passed, why not) for one phrasing."""
	frappe.db.savepoint("iran_eval")
	try:
		reply = run_case(turns, ai_available)
	except Exception as e:
		frappe.db.rollback(save_point="iran_eval")
		return False, f"error: {e}"
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
	frappe.db.rollback(save_point="iran_eval")
	return not problems, "; ".join(problems)


def evaluate(ai_available: bool = False) -> dict:
	results = []
	for case in CASES:
		for turns in case["phrasings"]:
			passed, why = check(case, turns, ai_available)
			results.append({"capability": case["capability"], "turns": turns, "passed": passed, "why": why})
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
