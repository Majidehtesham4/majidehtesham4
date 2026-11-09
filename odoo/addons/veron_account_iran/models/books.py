"""The legal books computed from the posted lines: the four-column trial balance at a level of the chart
(group: the first two digits of the code, ledger: four, sub-ledger: the account), the journal book by
voucher and the general ledger book by ledger account, each in Shamsi"""

from collections import OrderedDict, defaultdict

from odoo import api, fields, models

from .account_move import shamsi

LEVELS = {"group": 2, "ledger": 4, "account": None}


class AccountIranBooks(models.AbstractModel):
	_name = "veron.account.iran.books"
	_description = "Iranian Legal Books"

	@api.model
	def _key(self, account, level):
		size = LEVELS[level]
		return account.code if not size else (account.code or "")[:size]

	@api.model
	def _names(self, company, keys, level):
		"""The names of the groups and ledgers of the chart, from its account groups"""
		if level == "account":
			return {}
		groups = self.env["account.group"].sudo().search([("company_id", "=", company.id),
			("code_prefix_start", "in", list(keys))])
		return {group.code_prefix_start: group.name for group in groups}

	@api.model
	def _lines(self, company, date_from=None, date_to=None, accounts=None):
		domain = [("company_id", "=", company.id), ("parent_state", "=", "posted")]
		if date_from:
			domain.append(("date", ">=", date_from))
		if date_to:
			domain.append(("date", "<=", date_to))
		if accounts:
			domain.append(("account_id", "in", accounts.ids))
		return self.env["account.move.line"].search(domain, order="date, move_id, id")

	@api.model
	def trial_balance(self, company, date_from, date_to, level="ledger"):
		"""Rows of (code, name, debit turnover, credit turnover, debit balance, credit balance); the balance is
		up to the end of the period, the turnover of the period only"""
		rows = defaultdict(lambda: {"name": "", "debit": 0.0, "credit": 0.0, "balance": 0.0})
		before = self._lines(company, date_to=fields.Date.subtract(fields.Date.to_date(date_from), days=1))
		for line in before:
			rows[self._key(line.account_id, level)]["balance"] += line.balance
			rows[self._key(line.account_id, level)]["name"] = line.account_id.name
		for line in self._lines(company, date_from, date_to):
			row = rows[self._key(line.account_id, level)]
			row["name"] = line.account_id.name
			row["debit"] += line.debit
			row["credit"] += line.credit
			row["balance"] += line.balance
		names = self._names(company, rows.keys(), level)
		result = []
		for code in sorted(rows):
			row = rows[code]
			if not (row["debit"] or row["credit"] or round(row["balance"], 2)):
				continue
			result.append({"code": code, "name": names.get(code) or row["name"], "debit": row["debit"],
				"credit": row["credit"], "balance_debit": max(row["balance"], 0.0), "balance_credit": max(-row["balance"], 0.0)})
		return result

	@api.model
	def journal_book(self, company, date_from, date_to):
		"""Each voucher of the period in its order, with its lines summed by ledger account"""
		vouchers = OrderedDict()
		for line in self._lines(company, date_from, date_to):
			move = line.move_id
			voucher = vouchers.setdefault(move.id, {"number": move.veron_voucher or move.name, "date": shamsi(move.date),
				"ref": move.ref or move.name, "rows": OrderedDict()})
			code = self._key(line.account_id, "ledger")
			row = voucher["rows"].setdefault(code, {"code": code, "debit": 0.0, "credit": 0.0})
			row["debit"] += line.debit
			row["credit"] += line.credit
		codes = {row["code"] for voucher in vouchers.values() for row in voucher["rows"].values()}
		names = self._names(company, codes, "ledger")
		result = []
		for voucher in sorted(vouchers.values(), key=lambda v: (v["date"], str(v["number"]))):
			rows = list(voucher["rows"].values())
			for row in rows:
				row["name"] = names.get(row["code"], row["code"])
			# The debits first, as a journal book is written
			voucher["rows"] = sorted(rows, key=lambda r: (r["credit"] > r["debit"], r["code"]))
			result.append(voucher)
		return result

	@api.model
	def general_ledger(self, company, date_from, date_to, codes=None):
		"""Each ledger account: its balance at the start, each voucher of the period with the running balance"""
		opening = defaultdict(float)
		for line in self._lines(company, date_to=fields.Date.subtract(fields.Date.to_date(date_from), days=1)):
			opening[self._key(line.account_id, "ledger")] += line.balance
		ledgers = OrderedDict()
		for line in self._lines(company, date_from, date_to):
			code = self._key(line.account_id, "ledger")
			if codes and code not in codes:
				continue
			entries = ledgers.setdefault(code, OrderedDict())
			move = line.move_id
			entry = entries.setdefault(move.id, {"date": shamsi(move.date), "number": move.veron_voucher or move.name,
				"ref": line.name or move.ref or "", "debit": 0.0, "credit": 0.0})
			entry["debit"] += line.debit
			entry["credit"] += line.credit
		names = self._names(company, set(ledgers) | set(opening), "ledger")
		result = []
		for code in sorted(set(ledgers) | {c for c, v in opening.items() if round(v, 2) and (not codes or c in codes)}):
			balance = opening.get(code, 0.0)
			rows = []
			for entry in ledgers.get(code, {}).values():
				balance += entry["debit"] - entry["credit"]
				rows.append(dict(entry, balance=abs(balance), side="بد" if balance > 0 else "بس" if balance < 0 else "-"))
			result.append({"code": code, "name": names.get(code, code), "opening": opening.get(code, 0.0), "rows": rows,
				"closing": balance})
		return result
