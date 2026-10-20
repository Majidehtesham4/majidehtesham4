"""The assistant's catalog of what it can do in the ERP, one entry per capability.

Each capability is a command of commands/catalog.py (its id is the command's name, its examples are
the ways people ask for it) with what the assistant needs to know to do it well:

- kind: «read» only reads; «draft» makes a record that is not final (a draft document, a login that is
  switched off) and links to it for review; «action» changes something and asks yes first;
  «navigate» only opens a page.
- tool: the handler that runs it and the ERP records, reports or APIs it uses.
- entities: the details it reads from the request; defaults: what it takes when they are not said
  (and says so in the answer); clarify: the only cases it asks a question.
- response, link, success: what the answer holds, where its links go, how a right answer is judged
  (commands/evaluation.py checks the intent, the details read and the link).
- permission: the record types the user must be allowed to read (or create).

Commands with no entry here still work; their kind is taken from their name (create_… → draft).
The AI model sees this catalog (find_capability) and runs a capability with the details it
understood (run_capability), so live figures always come from these handlers, not from the model.
"""

import frappe

CAPABILITIES = {
	"investor_info": {
		"kind": "read",
		"tool": "insight.investor_info → Iran Investor, Iran Investment Contract, investor_portal.get_my_account",
		"entities": {"investor": "an investor by name or code", "name": "a name typed that is not on record"},
		"defaults": "no name: every investor with their active capital",
		"clarify": "several investors match the name: they are listed to choose from",
		"response": "the investor's details, capital, profit to date, what is still owed, next payment, contracts",
		"link": "the investor's file, their account page, their contracts",
		"success": "the named investor's real record; never a login or an invoice",
		"permission": ["Iran Investor", "Iran Investment Contract"],
	},
	"car_stock": {
		"kind": "read",
		"tool": "insight.car_stock → Iran Vehicle (in the lot: awaiting delivery, in preparation, ready, reserved)",
		"entities": {"branch": "a branch", "ownership": "امانی / خود نمایشگاه / سرمایه‌گذار in the words", "status": "آماده فروش"},
		"defaults": "every branch and owner, cars still in the lot",
		"clarify": "never",
		"response": "count by status, owner and branch, total asking price, the newest cars",
		"link": "the car list with the same filters, the dealership dashboard",
		"success": "the cars of the lot with the filters said",
		"permission": ["Iran Vehicle"],
	},
	"stock_balance": {
		"kind": "read",
		"tool": "stock.stock_balance → Bin; report Stock Balance / Stock Ledger",
		"entities": {"item": "an item", "warehouse": "a warehouse"},
		"defaults": "nothing named: every warehouse (a dealership: the cars in the lot)",
		"clarify": "never; several items with one name are listed to choose from",
		"response": "quantity per warehouse, or the most valuable items",
		"link": "Stock Ledger of the item, or Stock Balance",
		"success": "real stock figures",
		"permission": ["Bin"],
	},
	"last_sales_invoices": {
		"kind": "read",
		"tool": "selling.last_sales_invoices → Sales Invoice",
		"entities": {"customer": "a customer", "period": "a period", "limit": "how many"},
		"defaults": "every customer, the latest 10 drafts and submitted invoices",
		"clarify": "never",
		"response": "a table of invoices with customer, date, total and status",
		"link": "the Sales Invoice list with the same filters",
		"success": "invoices from the ERP; an empty period is said, not «nothing found» for no period",
		"permission": ["Sales Invoice"],
	},
	"receivables": {
		"kind": "read",
		"tool": "accounts.receivables → GL Entry balances of customers; report Accounts Receivable",
		"entities": {},
		"defaults": "every customer, today",
		"clarify": "never",
		"response": "total owed by customers and the largest balances",
		"link": "Accounts Receivable report",
		"success": "customers' balances from the ledger",
		"permission": ["GL Entry"],
	},
	"party_statement": {
		"kind": "read",
		"tool": "accounts.party_statement → GL Entry; reports General Ledger, Customer/Supplier Ledger Summary",
		"entities": {"party": "a customer or supplier, or «همه»", "period": "a period"},
		"defaults": "this Jalali year; «مشتریان» or «همه»: every customer",
		"clarify": "no party and no «همه»: asks which, with «همه» as an answer",
		"response": "movements and balance (Dr: they owe us)",
		"link": "General Ledger of the party, or Customer Ledger Summary",
		"success": "«همه» runs every customer's statement without asking again",
		"permission": ["GL Entry"],
	},
	"balance": {
		"kind": "read",
		"tool": "accounts.balance → erpnext get_balance_on; General Ledger",
		"entities": {"party": "a customer, supplier or account"},
		"defaults": "today",
		"clarify": "several parties with the name are listed",
		"response": "who owes whom, and the side of the account in the company's books (بدهکار/بستانکار)",
		"link": "the party's General Ledger, their unpaid invoices",
		"success": "the ledger balance, with the company's point of view said",
		"permission": ["GL Entry"],
	},
	"create_investor_login": {
		"kind": "draft",
		"tool": "admin.create_investor_login → users.investor_login (User with the Investor role, switched off)",
		"entities": {"investor": "the investor", "username": "username", "password": "password the operator gives"},
		"defaults": "none",
		"clarify": "which investor, the username and the password when not said",
		"response": "the login prepared, switched off; the password is never repeated",
		"link": "the user's form, to check and tick «Enabled»",
		"success": "a switched-off login linked to the investor; changing an existing login asks yes first",
		"permission": ["User (System Manager or Accounts Manager)"],
	},
	"create_user_login": {
		"kind": "draft",
		"tool": "admin.create_user_login → users.create_user (roles by what the person does), switched off",
		"entities": {"kind": "what they do", "name": "full name", "username": "username", "password": "password", "branch": "branch"},
		"defaults": "the only branch, when there is one",
		"clarify": "what the person does (it decides the roles), then whatever else is missing",
		"response": "the login prepared, switched off; the password is never repeated",
		"link": "the user's form, to check the roles and tick «Enabled»",
		"success": "a switched-off login with the roles of its kind",
		"permission": ["User (System Manager)"],
	},
	"set_user_password": {
		"kind": "action",
		"tool": "admin.set_user_password → users.set_password",
		"entities": {"user": "a login by name, username or email", "password": "the new password"},
		"defaults": "none",
		"clarify": "which login and the password when not said; asks yes before changing",
		"response": "done, without repeating the password",
		"link": "the user's form",
		"success": "changed only after yes",
		"permission": ["User (System Manager)"],
	},
	"create_sales_invoice": {
		"kind": "draft",
		"tool": "selling.create_sales_invoice → Sales Invoice (draft)",
		"entities": {"customer": "customer", "items": "items, quantities, prices", "vat": "VAT or not"},
		"defaults": "today, the default warehouse and price list",
		"clarify": "customer and items when missing; whether VAT applies",
		"response": "the draft with its total",
		"link": "the draft invoice, to review and submit in the ERP",
		"success": "a draft only; never submitted from the chat",
		"permission": ["Sales Invoice (create)"],
	},
}

# Intents that change something and ask yes first
ACTIONS = {"set_user_password"}


def kind_of(name: str) -> str:
	if name in CAPABILITIES:
		return CAPABILITIES[name]["kind"]
	if name in ACTIONS:
		return "action"
	if name.startswith(("create_", "new_")):
		return "draft"
	if name.startswith(("open_",)):
		return "navigate"
	return "read"


def catalog() -> list[dict]:
	"""Every capability: its command with the catalog's knowledge about it."""
	from iran_erp.commands.catalog import INTENTS

	out = []
	for intent in INTENTS:
		meta = CAPABILITIES.get(intent["name"], {})
		out.append(
			{
				"id": intent["name"],
				"title": intent["title"],
				"group": intent["group"],
				"kind": kind_of(intent["name"]),
				"examples": intent["examples"],
				"parameters": {slot: kind for slot, kind, _required, _question in intent.get("slots", [])},
				**{k: v for k, v in meta.items() if k != "kind"},
			}
		)
	return out


# ---------------------------------------------------------------- for the AI model


def find_capability(request: str, limit: int = 3) -> dict:
	"""The capabilities closest to a request, so the AI model can run one instead of composing the
	answer from raw searches."""
	from iran_erp.commands.engine import _without_names, get_matcher

	by_id = {c["id"]: c for c in catalog()}
	ranked = [r for r in get_matcher().rank(_without_names(request), limit=8) if r[0] in by_id][:limit]
	return {
		"capabilities": [
			{
				"id": name,
				"score": score,
				"title": by_id[name]["title"],
				"kind": by_id[name]["kind"],
				"parameters": by_id[name]["parameters"],
				"defaults": by_id[name].get("defaults", ""),
				"example": by_id[name]["examples"][0],
			}
			for name, score, _values in ranked
		]
	}


def run_capability(capability: str, request: str = "", parameters: dict | None = None) -> dict:
	"""Run a capability with the details the AI model understood. Each detail is given as the user
	would say it («آقای کریمی», «امسال», «همه») and read by the same readers as a typed request,
	so names become records. A capability that needs a yes, or a detail still missing, returns the
	question for the user; it is never confirmed from here."""
	from iran_erp.commands import engine
	from iran_erp.commands import slots as slot_readers

	if capability not in engine.INTENT_BY_NAME:
		return {"error": f"Unknown capability {capability}. Call find_capability first."}
	values = {}
	types = {slot: kind for slot, kind, _required, _question in engine._slots(capability)}
	for slot, text in (parameters or {}).items():
		if slot not in types or text in (None, ""):
			continue
		if str(text).strip() in ("*", "همه"):
			values[slot] = "*"
			continue
		if types[slot] in ("name", "text", "password", "username"):
			values[slot] = str(text)
			continue
		message = slot_readers.Message(str(text))
		message.answering = slot
		try:
			value = slot_readers.extract(types[slot], message, slot)
		except slot_readers.Ambiguous as e:
			return {"question": f"Several records match «{text}» for {slot}", "options": [label for _v, label in e.options]}
		if value in (None, ""):
			return {"error": f"«{text}» was not found as {types[slot]}. Ask the user, or search for it."}
		values[slot] = value
	result = engine._run(capability, values, slot_readers.Message(request or ""), ai_available=False)
	state = result.get("state") or {}
	out = {"answer": result.get("answer"), "links": result.get("actions") or []}
	if state.get("confirm"):
		out["needs_confirmation"] = (
			"Not done: this changes something. Tell the user what will change and ask them to confirm "
			"by sending the same request to the assistant again and answering yes, or to do it in the ERP."
		)
	elif state.get("waiting"):
		out["question_for_user"] = result.get("answer")
		out["options"] = [label for _v, label in (state.get("options") or [])]
	return out


def markdown() -> str:
	"""The catalog as a page (docs/capabilities.md): bench execute iran_erp.commands.capabilities.markdown"""
	kinds = {"read": "فقط خواندنی", "draft": "پیش‌نویس", "action": "تغییر با تأیید", "navigate": "باز کردن صفحه"}
	lines = ["# قابلیت‌های دستیار", "", "این صفحه از `iran_erp/commands/capabilities.py` ساخته می‌شود.", ""]
	for c in catalog():
		if c["id"] not in CAPABILITIES:
			continue
		lines += [f"## {c['title']} (`{c['id']}`)", "", f"- نوع: {kinds[c['kind']]}"]
		for key, label in (
			("tool", "ابزار"),
			("defaults", "پیش‌فرض"),
			("clarify", "سؤال فقط وقتی"),
			("response", "پاسخ"),
			("link", "لینک"),
			("success", "معیار موفقیت"),
		):
			if c.get(key):
				lines.append(f"- {label}: {c[key]}")
		if c.get("entities"):
			lines.append("- جزئیات: " + "، ".join(f"`{k}` ({v})" for k, v in c["entities"].items()))
		if c.get("permission"):
			lines.append("- دسترسی لازم: " + "، ".join(c["permission"]))
		lines += ["- نمونه درخواست‌ها:"] + [f"  - «{e}»" for e in c["examples"][:6]] + [""]
	others = [c for c in catalog() if c["id"] not in CAPABILITIES]
	lines += ["## بقیه‌ی دستورها", ""] + [f"- {c['title']} (`{c['id']}`، {kinds[c['kind']]})" for c in others]
	return "\n".join(lines) + "\n"
