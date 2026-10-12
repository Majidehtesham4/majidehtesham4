"""Match a bank statement against the bank account's ledger."""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from iran_erp.ai.files import get_file, parse_amount, parse_date, read_table

MAX_LISTED = 100


def statement_lines(rows: list[list], headers: list, columns: dict) -> list[dict]:
	"""Turn table rows into statement lines using the column mapping chosen by the model."""

	def index(key):
		name = columns.get(key)
		if name in (None, ""):
			return None
		if isinstance(name, int):
			return name
		if name not in headers:
			frappe.throw(
				_("Column {0} is not in the statement. Columns: {1}").format(
					name, ", ".join(map(str, headers))
				)
			)
		return headers.index(name)

	idx = {
		key: index(key)
		for key in ("date", "description", "deposit", "withdrawal", "amount", "reference", "balance")
	}
	if idx["date"] is None or (
		idx["amount"] is None and idx["deposit"] is None and idx["withdrawal"] is None
	):
		frappe.throw(
			_("Map at least the date column and either an amount column or deposit and withdrawal columns.")
		)

	def cell(row, key):
		i = idx[key]
		return row[i] if i is not None and i < len(row) else None

	lines = []
	for number, row in enumerate(rows, start=1):
		date = parse_date(cell(row, "date"))
		if not date:
			continue
		if idx["amount"] is not None:
			amount = parse_amount(cell(row, "amount")) or 0
		else:
			amount = (parse_amount(cell(row, "deposit")) or 0) - abs(
				parse_amount(cell(row, "withdrawal")) or 0
			)
		if not amount:
			continue
		lines.append(
			{
				"row": number,
				"date": date,
				"amount": amount,
				"description": str(cell(row, "description") or "")[:200],
				"reference": str(cell(row, "reference") or "").strip(),
				"balance": parse_amount(cell(row, "balance")),
			}
		)
	return lines


def ledger_entries(account: str, from_date, to_date) -> list[dict]:
	"""Net movement on the bank account per voucher, with the voucher's reference number."""
	entries = frappe.db.sql(
		"""
		select voucher_type, voucher_no, posting_date, sum(debit) - sum(credit) as amount
		from `tabGL Entry`
		where account = %s and is_cancelled = 0 and posting_date between %s and %s
		group by voucher_type, voucher_no, posting_date
		having amount != 0
		order by posting_date
		""",
		(account, from_date, to_date),
		as_dict=True,
	)
	for entry in entries:
		entry.reference = ""
		if entry.voucher_type == "Payment Entry":
			entry.reference = frappe.db.get_value("Payment Entry", entry.voucher_no, "reference_no") or ""
		elif entry.voucher_type == "Journal Entry":
			entry.reference = frappe.db.get_value("Journal Entry", entry.voucher_no, "cheque_no") or ""
	return entries


def match(lines: list[dict], entries: list[dict], tolerance_days: int) -> tuple[list, list, list]:
	"""Pair each statement line with one ledger entry of the same signed amount within the date window.

	A matching reference number wins; otherwise the closest date does.
	"""
	unused = list(entries)
	matched, unmatched = [], []
	for line in sorted(lines, key=lambda line: line["date"]):
		candidates = [
			entry
			for entry in unused
			if abs(flt(entry.amount) - line["amount"]) < 0.5
			and abs((getdate(entry.posting_date) - line["date"]).days) <= tolerance_days
		]
		if not candidates:
			unmatched.append(line)
			continue

		def score(entry):
			same_reference = (
				bool(line["reference"])
				and entry.reference
				and (entry.reference in line["reference"] or line["reference"] in entry.reference)
			)
			return (0 if same_reference else 1, abs((getdate(entry.posting_date) - line["date"]).days))

		best = min(candidates, key=score)
		unused.remove(best)
		matched.append((line, best))
	return matched, unmatched, unused


def match_bank_statement(
	file_url: str,
	bank_account: str,
	date_column: str,
	deposit_column: str | None = None,
	withdrawal_column: str | None = None,
	amount_column: str | None = None,
	description_column: str | None = None,
	reference_column: str | None = None,
	balance_column: str | None = None,
	header_row: int = 1,
	tolerance_days: int = 3,
):
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("No permission to read {0}").format(_("GL Entry")))
	account = frappe.db.get_value("Account", bank_account, ["account_type", "is_group"], as_dict=True)
	if not account or account.is_group or account.account_type not in ("Bank", "Cash"):
		frappe.throw(_("{0} is not a bank account").format(bank_account))

	table = read_table(get_file(file_url))
	header_row = max(int(header_row or 1), 1)
	headers = [str(h).strip() if h is not None else "" for h in table[header_row - 1]]
	columns = {
		"date": date_column,
		"deposit": deposit_column,
		"withdrawal": withdrawal_column,
		"amount": amount_column,
		"description": description_column,
		"reference": reference_column,
		"balance": balance_column,
	}
	lines = statement_lines(table[header_row:], headers, columns)
	if not lines:
		frappe.throw(_("No dated lines with an amount were found with this column mapping."))

	tolerance_days = min(max(int(tolerance_days or 0), 0), 15)
	start = min(line["date"] for line in lines)
	end = max(line["date"] for line in lines)
	entries = ledger_entries(bank_account, add_days(start, -tolerance_days), add_days(end, tolerance_days))
	matched, unmatched_lines, unmatched_entries = match(lines, entries, tolerance_days)

	ledger_balance = flt(
		frappe.db.sql(
			"select sum(debit) - sum(credit) from `tabGL Entry` where account=%s and is_cancelled=0 and posting_date <= %s",
			(bank_account, end),
		)[0][0]
	)
	last_with_balance = next(
		(
			line
			for line in sorted(lines, key=lambda line: (line["date"], line["row"]), reverse=True)
			if line["balance"] is not None
		),
		None,
	)

	def line_out(line):
		return {k: _date(v) for k, v in line.items() if k != "balance"}

	def entry_out(entry):
		return {
			"voucher_type": entry.voucher_type,
			"voucher_no": entry.voucher_no,
			"date": _date(entry.posting_date),
			"amount": flt(entry.amount),
			"reference": entry.reference,
		}

	return {
		"bank_account": bank_account,
		"period": [_date(start), _date(end)],
		"statement_lines": len(lines),
		"matched": len(matched),
		"statement_total": sum(line["amount"] for line in lines),
		"ledger_total_in_period": sum(
			flt(e.amount) for e in entries if start <= getdate(e.posting_date) <= end
		),
		"statement_closing_balance": last_with_balance["balance"] if last_with_balance else None,
		"ledger_balance_at_end": ledger_balance,
		"unmatched_statement_lines": [line_out(line) for line in unmatched_lines[:MAX_LISTED]],
		"unmatched_ledger_entries": [
			entry_out(e) for e in unmatched_entries if start <= getdate(e.posting_date) <= end
		][:MAX_LISTED],
		"matched_examples": [
			{"line": line_out(line), "entry": entry_out(entry)} for line, entry in matched[:20]
		],
	}


def _date(value):
	if isinstance(value, datetime.date):
		from iran_erp.utils.jalali import format_jalali

		return f"{value:%Y-%m-%d} ({format_jalali(value, persian_digits=False)})"
	return value
