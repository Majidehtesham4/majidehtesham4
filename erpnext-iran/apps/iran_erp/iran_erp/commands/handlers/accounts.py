import frappe
from frappe import _
from frappe.utils import flt, nowdate

from iran_erp.ai.tools import get_url_to_form
from iran_erp.commands import entities
from iran_erp.commands.engine import Delegate, NeedSlot
from iran_erp.commands.handlers import (
	company,
	doc_link,
	document_list,
	jdate,
	link,
	list_url,
	money,
	number,
	party_label,
	party_of,
	period_or,
	report_url,
	require,
	table,
)


def _balance_on(**kwargs):
	from erpnext.accounts.utils import get_balance_on

	return flt(get_balance_on(company=company(), **kwargs))


def balance(context):
	require("GL Entry")
	if not context.get("party"):
		# «بدهی مشتری‌ها», «طلب تامین‌کننده‌ها»: everyone's
		words = set(context.message.words)
		if words & {"مشتریها", "مشتریان", "مشتری‌ها", "مشتریا"}:
			return receivables(context)
		if words & {"تامینکنندگان", "تامین‌کنندگان", "تامینکنندهها", "تامین‌کننده‌ها", "فروشندهها"}:
			return payables(context)
		raise NeedSlot("party", _("Balance of whom, or which account?"))
	doctype, name = party_of(context.get("party"))
	if doctype == "Account":
		value = _balance_on(account=name)
		return {
			"answer": _("Balance of {0}: {1}").format(name, money(value)),
			"actions": [
				link(
					_("General Ledger"),
					report_url("General Ledger", {"company": company(), "account": f'["{name}"]'}),
				)
			],
		}
	value = _balance_on(party_type=doctype, party=name)
	label = party_label(doctype, name)
	if abs(value) < 1:
		text = _("{0} has no balance; the account is settled.").format(label)
	elif value > 0:
		text = _("{0} owes us {1}.").format(label, money(value))
	else:
		text = _("We owe {0} {1}.").format(label, money(-value))
	# «بستانکار / بدهکار» are the side of the account in the company's books
	if abs(value) >= 1:
		text += "\n\n" + _("In the company's books the account of {0} is {1} {2}.").format(
			label, money(abs(value)), _("debit (they owe us)") if value > 0 else _("credit (we owe them)")
		)
	field = "customer" if doctype == "Customer" else "supplier"
	invoice_doctype = "Sales Invoice" if doctype == "Customer" else "Purchase Invoice"
	unpaid = frappe.get_list(
		invoice_doctype,
		filters={field: name, "docstatus": 1, "outstanding_amount": [">", 0]},
		fields=[{"COUNT": "name", "as": "n"}, {"SUM": "outstanding_amount", "as": "total"}],
	)
	if unpaid and unpaid[0].n:
		text += "\n\n" + _("Unpaid invoices: {0}, totalling {1}.").format(
			number(unpaid[0].n), money(unpaid[0].total)
		)
	return {
		"answer": text,
		"actions": [
			link(
				_("Statement"),
				report_url(
					"General Ledger", {"company": company(), "party_type": doctype, "party": f'["{name}"]'}
				),
			),
			link(
				_("Unpaid invoices"),
				list_url(invoice_doctype, {field: name, "docstatus": 1, "outstanding_amount": [">", 0]}),
			),
		],
	}


def party_statement(context):
	require("GL Entry")
	from iran_erp.commands.handlers.insight import all_statements, wants_everyone

	# «صورتحساب مشتریان», or «همه» as the answer: everyone's at once
	if wants_everyone(context):
		return all_statements(context)
	if not context.get("party"):
		raise NeedSlot("party", _("Statement of which customer or supplier? (or «همه» for all customers)"))
	doctype, name = party_of(context.get("party"))
	start, end, label = period_or(context, "year")
	rows = frappe.db.sql(
		"""select posting_date, voucher_type, voucher_no, sum(debit) debit, sum(credit) credit
		from `tabGL Entry`
		where company=%s and party_type=%s and party=%s and is_cancelled=0 and posting_date between %s and %s
		group by voucher_type, voucher_no, posting_date
		order by posting_date desc, voucher_no desc limit 15""",
		(company(), doctype, name, start, end),
		as_dict=True,
	)
	closing = _balance_on(party_type=doctype, party=name)
	lines = [f"**{_('Statement of {0}').format(party_label(doctype, name))}** ({label})", ""]
	if rows:
		lines.append(
			table(
				[_("Date"), _("Document"), _("Debit"), _("Credit")],
				[
					[
						jdate(r.posting_date),
						f"[{r.voucher_no}]({get_url_to_form(r.voucher_type, r.voucher_no)})",
						money(r.debit) if r.debit else "",
						money(r.credit) if r.credit else "",
					]
					for r in rows
				],
			)
		)
	else:
		lines.append(_("No transactions in this period."))
	lines.append("\n" + _("Balance today: {0}").format(money(closing)))
	url = report_url(
		"General Ledger",
		{
			"company": company(),
			"from_date": start,
			"to_date": end,
			"party_type": doctype,
			"party": f'["{name}"]',
			"group_by": "Group by Voucher (Consolidated)",
		},
	)
	return {"answer": "\n".join(lines), "actions": [link(_("Full statement"), url)]}


def bank_accounts() -> dict[str, str]:
	"""The company's bank accounts as {ledger account: name people know it by, e.g. "بانک ملت شرکا"}."""
	if not frappe.has_permission("Bank Account", "read"):
		return {}
	rows = frappe.get_list(
		"Bank Account",
		filters={"company": company(), "is_company_account": 1, "disabled": 0},
		fields=["name", "account"],
	)
	return {row.account: row.name for row in rows if row.account}


def cash_position(context):
	require("GL Entry")
	bank = context.get("bank")
	account = frappe.db.get_value("Bank Account", bank, "account") if bank else context.get("account")
	names = bank_accounts()
	accounts = (
		[account]
		if account
		else frappe.get_list(
			"Account",
			filters={
				"company": company(),
				"is_group": 0,
				"account_type": ["in", ["Cash", "Bank"]],
				"disabled": 0,
			},
			pluck="name",
			order_by="lft asc",
		)
	)
	rows, total_value = [], 0
	for name in accounts:
		value = _balance_on(account=name)
		total_value += value
		label = name.rsplit(" - ", 1)[0]
		if names.get(name):
			label += f" ({names[name]})"
		rows.append([label, money(value)])
	answer = table([_("Account"), _("Balance")], rows)
	if len(rows) > 1:
		answer += "\n\n" + _("Total cash and bank: {0}").format(money(total_value))
	return {"answer": answer or _("No cash or bank accounts found."), "actions": []}


def _party_balances(party_type: str):
	return frappe.db.sql(
		"""select party, sum(debit) - sum(credit) balance from `tabGL Entry`
		where company=%s and party_type=%s and is_cancelled=0
		group by party having abs(balance) >= 1 order by balance desc""",
		(company(), party_type),
		as_dict=True,
	)


def receivables(context):
	require("GL Entry")
	rows = [r for r in _party_balances("Customer") if r.balance > 0]
	if not rows:
		return _("No customer owes us anything.")
	total_value = sum(r.balance for r in rows)
	answer = _("Customers owe us {0} in total ({1} customers).").format(money(total_value), number(len(rows)))
	answer += "\n\n" + table(
		[_("Customer"), _("Balance")],
		[[party_label("Customer", r.party), money(r.balance)] for r in rows[:10]],
	)
	return {
		"answer": answer,
		"actions": [
			link(_("Accounts Receivable"), report_url("Accounts Receivable", {"company": company()}))
		],
	}


def payables(context):
	require("GL Entry")
	rows = sorted((r for r in _party_balances("Supplier") if r.balance < 0), key=lambda r: r.balance)
	if not rows:
		return _("We owe no supplier anything.")
	total_value = -sum(r.balance for r in rows)
	answer = _("We owe suppliers {0} in total ({1} suppliers).").format(money(total_value), number(len(rows)))
	answer += "\n\n" + table(
		[_("Supplier"), _("Balance")],
		[[party_label("Supplier", r.party), money(-r.balance)] for r in rows[:10]],
	)
	return {
		"answer": answer,
		"actions": [link(_("Accounts Payable"), report_url("Accounts Payable", {"company": company()}))],
	}


def _overdue(doctype, party_field, party, title):
	filters = {"docstatus": 1, "outstanding_amount": [">", 0], "company": company()}
	if party:
		filters[party_field] = party
	result = document_list(
		doctype,
		filters,
		[
			("name", _("Invoice"), "link"),
			(f"{party_field}_name", _(party_field.title()), ""),
			("due_date", _("Due Date"), "date"),
			("outstanding_amount", _("Outstanding"), "money"),
		],
		title,
		order_by="due_date asc",
		empty=_("No unpaid invoices."),
	)
	unpaid_total = frappe.get_list(
		doctype, filters=filters, fields=[{"SUM": "outstanding_amount", "as": "total"}]
	)
	overdue = frappe.get_list(
		doctype,
		filters={**filters, "due_date": ["<", nowdate()]},
		fields=[{"SUM": "outstanding_amount", "as": "total"}],
	)
	if unpaid_total and unpaid_total[0].total:
		result["answer"] += "\n\n" + _("Unpaid in total: {0}; past their due date: {1}.").format(
			money(unpaid_total[0].total), money(overdue[0].total if overdue else 0)
		)
	return result


def overdue_sales(context):
	return _overdue("Sales Invoice", "customer", context.get("customer"), _("Unpaid sales invoices"))


def overdue_purchases(context):
	return _overdue("Purchase Invoice", "supplier", context.get("supplier"), _("Unpaid purchase invoices"))


def _income_expense(start, end):
	return frappe.db.sql(
		"""select acc.root_type, gle.account, sum(gle.debit) debit, sum(gle.credit) credit
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company=%s and gle.is_cancelled=0 and gle.posting_date between %s and %s
			and acc.root_type in ('Income', 'Expense')
		group by acc.root_type, gle.account""",
		(company(), start, end),
		as_dict=True,
	)


def profit_loss(context):
	require("GL Entry")
	start, end, label = period_or(context, "year")
	rows = _income_expense(start, end)
	income = sum(r.credit - r.debit for r in rows if r.root_type == "Income")
	expense = sum(r.debit - r.credit for r in rows if r.root_type == "Expense")
	profit = income - expense
	lines = [
		f"**{_('Profit and Loss')}** ({label})",
		"",
		f"- {_('Income')}: {money(income)}",
		f"- {_('Expenses')}: {money(expense)}",
		f"- {_('Net profit') if profit >= 0 else _('Net loss')}: **{money(abs(profit))}**",
	]
	if income:
		lines.append(f"- {_('Profit margin')}: {number(profit / income * 100)}٪")
	url = report_url(
		"Profit and Loss Statement",
		{
			"company": company(),
			"period_start_date": start,
			"period_end_date": end,
			"filter_based_on": "Date Range",
			"periodicity": "Monthly",
		},
	)
	return {"answer": "\n".join(lines), "actions": [link(_("Profit and Loss Statement"), url)]}


def expenses(context):
	require("GL Entry")
	start, end, label = period_or(context)
	rows = [r for r in _income_expense(start, end) if r.root_type == "Expense"]
	rows = sorted(((r.account, r.debit - r.credit) for r in rows), key=lambda r: r[1], reverse=True)
	total_value = sum(v for _a, v in rows)
	if not rows:
		return _("No expenses in {0}.").format(label)
	answer = (
		_("Expenses in {0}: {1}").format(label, money(total_value))
		+ "\n\n"
		+ table([_("Account"), _("Amount")], [[a.rsplit(" - ", 1)[0], money(v)] for a, v in rows[:10]])
	)
	return {
		"answer": answer,
		"actions": [
			link(
				_("General Ledger"),
				report_url("General Ledger", {"company": company(), "from_date": start, "to_date": end}),
			)
		],
	}


def vat_report(context):
	require("Sales Invoice")
	start, end, label = period_or(context)
	totals = {}
	for doctype, child in (
		("Sales Invoice", "Sales Taxes and Charges"),
		("Purchase Invoice", "Purchase Taxes and Charges"),
	):
		if not frappe.has_permission(doctype, "read"):
			continue
		row = frappe.db.sql(
			f"""select sum(tax.base_tax_amount_after_discount_amount) tax, sum(inv.base_net_total) net
			from `tab{child}` tax join `tab{doctype}` inv on inv.name = tax.parent
			where tax.parenttype=%s and inv.docstatus=1 and inv.company=%s and inv.posting_date between %s and %s""",
			(doctype, company(), start, end),
			as_dict=True,
		)[0]
		totals[doctype] = (flt(row.tax), flt(row.net))
	output, input_ = totals.get("Sales Invoice", (0, 0))[0], totals.get("Purchase Invoice", (0, 0))[0]
	lines = [
		f"**{_('VAT')}** ({label})",
		"",
		f"- {_('VAT on sales')}: {money(output)}",
		f"- {_('VAT on purchases')}: {money(input_)}",
		f"- {_('VAT payable') if output >= input_ else _('VAT receivable')}: **{money(abs(output - input_))}**",
	]
	return "\n".join(lines)


def _payments(context, payment_type, party_type, party):
	require("Payment Entry")
	start, end, label = period_or(context)
	filters = {
		"docstatus": 1,
		"payment_type": payment_type,
		"company": company(),
		"posting_date": ["between", [start, end]],
	}
	if party:
		filters.update(party_type=party_type, party=party)
	result = document_list(
		"Payment Entry",
		filters,
		[
			("posting_date", _("Date"), "date"),
			("party_name", _("Party"), ""),
			("mode_of_payment", _("Mode of Payment"), "status"),
			("paid_amount", _("Amount"), "money"),
		],
		(_("Payments received") if payment_type == "Receive" else _("Payments made")) + f" ({label})",
		order_by="posting_date desc",
		empty=_("Nothing in {0}.").format(label),
	)
	summed = frappe.get_list(
		"Payment Entry", filters=filters, fields=[{"SUM": "base_paid_amount", "as": "total"}]
	)
	if summed and summed[0].total:
		result["answer"] += "\n\n" + _("Total: {0}").format(money(summed[0].total))
	return result


def payments_received(context):
	return _payments(context, "Receive", "Customer", context.get("customer"))


def payments_made(context):
	return _payments(context, "Pay", "Supplier", context.get("supplier"))


def _payment_entry(context, payment_type, party_type, party):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
	from erpnext.accounts.party import get_party_account

	require("Payment Entry", "create")
	mode = context.get("payment_mode")
	bank = context.get("bank")
	# Money that went into a named bank account was a transfer, not cash
	if bank and not mode:
		mode = "Wire Transfer"
	if not mode:
		raise NeedSlot("payment_mode", _("Was it paid in cash, or by bank transfer / card?"))
	if not frappe.db.exists("Mode of Payment", mode):
		mode = "Cash"
	the_company = company()
	amount = flt(context.get("amount"))
	try:
		account = get_bank_cash_account(mode, the_company).get("account")
	except frappe.ValidationError:
		frappe.clear_last_message()
		account = None
	if bank:
		account = frappe.db.get_value("Bank Account", bank, "account") or account
	if not account:
		field = "default_cash_account" if mode == "Cash" else "default_bank_account"
		account = frappe.get_cached_value("Company", the_company, field) or frappe.get_cached_value(
			"Company", the_company, "default_cash_account"
		)
	party_account = get_party_account(party_type, party, the_company)
	doc = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": payment_type,
			"company": the_company,
			"posting_date": nowdate(),
			"mode_of_payment": mode,
			"party_type": party_type,
			"party": party,
			"paid_from": party_account if payment_type == "Receive" else account,
			"paid_to": account if payment_type == "Receive" else party_account,
			"paid_amount": amount,
			"received_amount": amount,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
		}
	)
	if bank:
		doc.bank_account = bank
	if frappe.get_cached_value("Account", account, "account_type") == "Bank":
		doc.reference_no = _("Recorded from chat")
		doc.reference_date = nowdate()
	doc.insert()
	verb = _("received from") if payment_type == "Receive" else _("paid to")
	return {
		"answer": _(
			"Draft payment: {0} {1} {2} ({3}). It is not allocated to invoices yet; open it, use «Get Outstanding Invoices» and submit."
		).format(money(amount), verb, party_label(party_type, party), bank or _(mode)),
		"actions": [doc_link("Payment Entry", doc.name)],
	}


def receive_payment(context):
	return _payment_entry(context, "Receive", "Customer", context.get("customer"))


def make_payment(context):
	return _payment_entry(context, "Pay", "Supplier", context.get("supplier"))


def journal_entry(context):
	# Without an AI model the best help is the empty form
	require("Journal Entry", "create")
	return {
		"answer": _(
			"Recording a journal entry needs the accounts chosen by hand. I opened a new journal entry for you."
		),
		"actions": [{**link(_("New Journal Entry"), list_url("Journal Entry") + "/new"), "open": True}],
	}


def create_fiscal_year(context):
	from iran_erp.api import create_jalali_fiscal_year

	require("Fiscal Year", "create")
	year = int(flt(context.get("number")))
	if year < 1300 or year > 1500:
		raise NeedSlot("number", _("Which Jalali year? For example 1406."))
	name = create_jalali_fiscal_year(year, company())
	return {"answer": _("Fiscal year {0} is ready.").format(name), "actions": [doc_link("Fiscal Year", name)]}


def moadian_pending(context):
	start, end, label = period_or(context, "year")
	filters = {
		"docstatus": 1,
		"company": company(),
		"posting_date": ["between", [start, end]],
		"iran_tax_id": ["is", "not set"],
	}
	return document_list(
		"Sales Invoice",
		filters,
		[
			("name", _("Invoice"), "link"),
			("customer_name", _("Customer"), ""),
			("posting_date", _("Date"), "date"),
			("grand_total", _("Total"), "money"),
		],
		_("Sales invoices without a Moadian tax ID") + f" ({label})",
		order_by="posting_date asc",
		empty=_("Every submitted sales invoice of {0} has a tax ID.").format(label),
	)
