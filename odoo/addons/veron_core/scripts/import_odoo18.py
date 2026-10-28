"""Brings a company from a backup of Odoo 17 or 18 (Community or Enterprise) into a database of this program: its
data, not its database, since a database opens only in its own version of Odoo.

Run inside the program's container by «odoo.ps1 import18 <backup> <database>» or «./veron import18 <backup>
<database>». The backup (the zip of the database manager, or its unpacked folder) is loaded into a database of
its own next to the others (<database>_odoo18); nothing in it is changed. Then, into <database>:

  the company: its name, address, codes and logo
  contacts, with their bank accounts
  product categories and products, with their cost and sale price
  the chart of accounts: each account of the old company found by its code, or added
  opening balances on one date: one journal entry, as a DRAFT: an accountant checks it and posts it
  stock on hand: counted quantities in the main warehouse, NOT applied: applied in Inventory by a person
  employees and departments, when Employees is installed

Running it again brings what is new and changes nothing twice. Nothing is posted or applied by it: the final
confirmation is always made in the program, by a person."""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from datetime import date

MODULE = "veron_import18"
PROFIT_AND_LOSS = ("income", "income_other", "expense", "expense_depreciation", "expense_direct_cost")
PARTNER_TYPES = ("asset_receivable", "liability_payable")
OPENING_REF = "Opening balances from Odoo %s (%s)"


def say(text=""):
	print(text, flush=True)


def text(value, lang="fa_IR"):
	"""A translated name of Odoo (a JSON of languages) in Persian when it has it, else in English"""
	if isinstance(value, str) and value.startswith("{"):
		try:
			value = json.loads(value)
		except ValueError:
			return value
	if isinstance(value, dict):
		return value.get(lang) or value.get("en_US") or next(iter(value.values()), "") or ""
	return value or ""


# --- the backup and the old database


class Backup:
	"""The zip of the database manager or its unpacked folder: the manifest, dump.sql and the filestore"""

	def __init__(self, path):
		self.path = path
		self.zip = None if os.path.isdir(path) else zipfile.ZipFile(path)

	def manifest(self):
		if self.zip:
			return json.loads(self.zip.read("manifest.json"))
		with open(os.path.join(self.path, "manifest.json"), encoding="utf-8") as handle:
			return json.load(handle)

	def dump(self, folder):
		if not self.zip:
			return os.path.join(self.path, "dump.sql")
		return self.zip.extract("dump.sql", folder)

	def file(self, store_fname):
		"""A file of the filestore; None when the backup was made without it"""
		name = "filestore/" + store_fname
		try:
			if self.zip:
				return self.zip.read(name)
			with open(os.path.join(self.path, name), "rb") as handle:
				return handle.read()
		except (KeyError, OSError):
			return None


class Old:
	"""The old database, read only, by SQL: its tables differ from version to version"""

	def __init__(self, dsn):
		import psycopg2
		import psycopg2.extras

		self.connection = psycopg2.connect(dsn)
		self.connection.set_session(readonly=True)
		self.cr = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
		self._columns = {}

	def columns(self, table):
		if table not in self._columns:
			self.cr.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s", (table,))
			self._columns[table] = {row["column_name"]: row["data_type"] for row in self.cr.fetchall()}
		return self._columns[table]

	def has(self, table, column=None):
		columns = self.columns(table)
		return bool(columns) and (column is None or column in columns)

	def rows(self, query, params=()):
		self.cr.execute(query, params)
		return self.cr.fetchall()

	def column(self, table, column, default="NULL", alias=None):
		"""The column in a SELECT, or a default when this version has no such column"""
		return f"{alias or table}.{column}" if self.has(table, column) else f"{default} AS {column}"


def load(backup, database, reload=False):
	"""The dump of the backup loaded into a database of its own, once"""
	import psycopg2

	host, user, password = os.environ.get("HOST", "db"), os.environ.get("USER", "odoo"), os.environ.get("PASSWORD", "odoo")
	admin = psycopg2.connect(host=host, user=user, password=password, dbname="postgres")
	admin.autocommit = True
	with admin.cursor() as cr:
		cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
		exists = bool(cr.fetchone())
		if exists and reload:
			cr.execute(f'DROP DATABASE "{database}"')
			exists = False
		if exists:
			say(f"The old database {database} is already loaded; it is read again (--reload loads it anew).")
		else:
			cr.execute(f"CREATE DATABASE \"{database}\" ENCODING 'UTF8' TEMPLATE template0")
	admin.close()
	if not exists:
		say(f"Loading the backup into {database} (a few minutes for a large company)...")
		with tempfile.TemporaryDirectory() as folder:
			dump = backup.dump(folder)
			result = subprocess.run(["psql", "-h", host, "-U", user, "-d", database, "-q", "-X", "-v", "ON_ERROR_STOP=0",
				"-f", dump], env=dict(os.environ, PGPASSWORD=password), capture_output=True, text=True)
		errors = [line for line in result.stderr.splitlines() if "ERROR" in line and "role" not in line]
		if errors:
			say(f"  {len(errors)} lines of the dump were not loaded; the first: {errors[0][:200]}")
	return f"host={host} user={user} password={password} dbname={database}"


# --- the import


class Import:
	def __init__(self, env, old, backup, version, company_id=None, on=None):
		self.env, self.old, self.backup, self.version = env, old, backup, version
		self.company = env.company
		self.Data = env["ir.model.data"]
		companies = old.rows("SELECT id, name FROM res_company ORDER BY id")
		if len(companies) > 1:
			say("The backup has %s companies: %s" % (len(companies), ", ".join(f"{c['id']}: {c['name']}" for c in companies)))
		self.old_company = next((c for c in companies if c["id"] == company_id), companies[0])
		self.cid = self.old_company["id"]
		say(f"The company brought over: {self.old_company['name']} (number {self.cid} of the backup)")
		self.on = on or date.today()
		self.counts = defaultdict(int)
		self.notes = []

	def note(self, text):
		if text not in self.notes:
			self.notes.append(text)

	# where each old record went, kept as an external id so that a second run finds it

	def _name(self, kind, old_id):
		return f"{kind}_{self.cid}_{old_id}"

	def found(self, model, kind, old_id):
		data = self.Data.search([("module", "=", MODULE), ("name", "=", self._name(kind, old_id))], limit=1)
		record = self.env[model].browse(data.res_id).exists() if data else self.env[model]
		return record.with_context(active_test=False)

	def remember(self, record, kind, old_id):
		self.Data.create({"module": MODULE, "name": self._name(kind, old_id), "model": record._name, "res_id": record.id,
			"noupdate": True})
		self.counts[kind] += 1
		return record

	def values(self, model, values):
		"""Only the fields the model has here: Odoo 19 has fewer fields on some models than 18"""
		fields = self.env[model]._fields
		return {key: value for key, value in values.items() if key in fields and value not in (None, "")}

	def mobile(self, values, mobile):
		if mobile and "mobile" not in self.env["res.partner"]._fields:
			# Odoo 19 has one phone number on a contact: the mobile goes there when the phone is empty
			values["phone"] = values.get("phone") or mobile
		elif mobile:
			values["mobile"] = mobile

	def country(self, country_id, state_id=None):
		result = {}
		if country_id:
			code = self.old.rows("SELECT code FROM res_country WHERE id = %s", (country_id,))
			country = self.env["res.country"].search([("code", "=", code[0]["code"])], limit=1) if code else None
			if country:
				result["country_id"] = country.id
				if state_id:
					state = self.old.rows("SELECT code FROM res_country_state WHERE id = %s", (state_id,))
					found = self.env["res.country.state"].search([("country_id", "=", country.id),
						("code", "=", state[0]["code"])], limit=1) if state else None
					if found:
						result["state_id"] = found.id
		return result

	def image(self, model, field, res_id):
		"""An image of the old database: from its filestore, or kept in the database itself"""
		rows = self.old.rows("SELECT store_fname, db_datas FROM ir_attachment WHERE res_model = %s AND res_field = %s "
			"AND res_id = %s ORDER BY id DESC LIMIT 1", (model, field, res_id))
		if not rows:
			return None
		data = self.backup.file(rows[0]["store_fname"]) if rows[0]["store_fname"] else rows[0]["db_datas"]
		return base64.b64encode(bytes(data)).decode() if data else None

	# the company

	def company_details(self):
		row = self.old.rows("SELECT c.partner_id, c.currency_id, p.* FROM res_company c JOIN res_partner p "
			"ON p.id = c.partner_id WHERE c.id = %s", (self.cid,))[0]
		values = self.values("res.company", {"name": row["name"], "street": row["street"], "street2": row["street2"],
			"city": row["city"], "zip": row["zip"], "phone": row["phone"], "email": row["email"], "website": row["website"],
			"vat": row["vat"], "company_registry": row.get("company_registry")})
		values.update(self.country(row["country_id"], row["state_id"]))
		logo = self.image("res.partner", "image_1920", row["partner_id"])
		if logo:
			values["logo"] = logo
		self.company.write(values)
		currency = self.old.rows("SELECT name FROM res_currency WHERE id = %s", (row["currency_id"],))[0]["name"]
		if currency != self.company.currency_id.name:
			self.note(f"The old company kept its accounts in {currency}, this one in "
				f"{self.company.currency_id.name}: the amounts are brought as they are.")
		self.found_partner = {row["partner_id"]: self.company.partner_id}
		say(f"  the company: {self.company.name}")

	# contacts

	def partners(self):
		users = "SELECT partner_id FROM res_users WHERE share IS NOT TRUE" if self.old.has("res_users", "share") else \
			"SELECT partner_id FROM res_users"
		rows = self.old.rows(f"SELECT id FROM res_partner WHERE active AND id NOT IN ({users}) AND id NOT IN "
			f"(SELECT partner_id FROM res_company) AND (company_id IS NULL OR company_id = %s) ORDER BY parent_id NULLS "
			f"FIRST, id", (self.cid,))
		for row in rows:
			self.partner(row["id"])
		say(f"  contacts: {self.counts['partner']} new")

	def partner(self, old_id):
		"""The contact here for a contact of the old database, made the first time it is needed"""
		if not old_id:
			return self.env["res.partner"]
		if old_id in self.found_partner:
			return self.found_partner[old_id]
		partner = self.found("res.partner", "partner", old_id)
		if not partner:
			row = self.old.rows("SELECT * FROM res_partner WHERE id = %s", (old_id,))[0]
			parent = self.partner(row["parent_id"]) if row["parent_id"] else self.env["res.partner"]
			values = self.values("res.partner", {"name": row["name"] or row.get("display_name") or "-",
				"is_company": row["is_company"], "type": row["type"] if row["type"] in ("contact", "invoice", "delivery",
				"other") else "contact", "street": row["street"], "street2": row["street2"], "city": row["city"],
				"zip": row["zip"], "phone": row["phone"], "email": row["email"], "website": row["website"],
				"vat": row["vat"], "ref": row["ref"], "comment": row["comment"], "function": row["function"],
				"customer_rank": row.get("customer_rank") or 0, "supplier_rank": row.get("supplier_rank") or 0,
				"parent_id": parent.id or None, "active": row["active"]})
			self.mobile(values, row.get("mobile"))
			values.update(self.country(row["country_id"], row["state_id"]))
			partner = self.remember(self.env["res.partner"].create(values), "partner", old_id)
		self.found_partner[old_id] = partner
		return partner

	def bank_accounts(self):
		if not self.old.has("res_partner_bank"):
			return
		bank_column = self.old.column("res_bank", "bic", "NULL", "b")
		rows = self.old.rows(f"SELECT a.id, a.acc_number, a.partner_id, b.name AS bank, {bank_column} FROM res_partner_bank a "
			f"LEFT JOIN res_bank b ON b.id = a.bank_id WHERE a.active IS NOT FALSE AND (a.company_id IS NULL OR "
			f"a.company_id = %s)", (self.cid,))
		for row in rows:
			if self.found("res.partner.bank", "bank", row["id"]):
				continue
			partner = self.partner(row["partner_id"])
			if not partner or not row["acc_number"]:
				continue
			twin = self.env["res.partner.bank"].search([("partner_id", "=", partner.id),
				("acc_number", "=", row["acc_number"])], limit=1)
			if twin:
				self.remember(twin, "bank", row["id"])
				continue
			bank = self.env["res.bank"]
			if row["bank"]:
				bank = bank.search([("name", "=", row["bank"])], limit=1) or bank.create(self.values("res.bank",
					{"name": row["bank"], "bic": row.get("bic")}))
			self.remember(self.env["res.partner.bank"].create({"partner_id": partner.id, "acc_number": row["acc_number"],
				"bank_id": bank.id or False}), "bank", row["id"])
		say(f"  bank accounts: {self.counts['bank']} new")

	# products

	def category(self, old_id):
		if not old_id:
			return self.env.ref("product.product_category_all", raise_if_not_found=False) or self.env["product.category"]
		category = self.found("product.category", "category", old_id)
		if category:
			return category
		row = self.old.rows("SELECT name, parent_id FROM product_category WHERE id = %s", (old_id,))[0]
		parent = self.category(row["parent_id"]) if row["parent_id"] else self.env["product.category"]
		name = text(row["name"])
		category = self.env["product.category"].search([("name", "=", name), ("parent_id", "=", parent.id or False)], limit=1)
		if not category:
			category = self.env["product.category"].create({"name": name, "parent_id": parent.id or False})
		return self.remember(category, "category", old_id)

	def uom(self, old_id):
		Uom = self.env["uom.uom"].with_context(lang="en_US")
		unit = self.env.ref("uom.product_uom_unit")
		if not old_id:
			return unit
		row = self.old.rows("SELECT name FROM uom_uom WHERE id = %s", (old_id,))
		if not row:
			return unit
		names = json.loads(row[0]["name"]) if isinstance(row[0]["name"], str) and row[0]["name"].startswith("{") else \
			row[0]["name"] if isinstance(row[0]["name"], dict) else {"en_US": row[0]["name"]}
		for name in [names.get("en_US")] + list(names.values()):
			found = Uom.search([("name", "=ilike", name)], limit=1) if name else None
			if found:
				return found
		self.note(f"The unit «{text(names)}» is not here; its products are in units.")
		return unit

	def standard_price(self, product_id):
		column = self.old.columns("product_product").get("standard_price")
		if column == "jsonb":
			row = self.old.rows("SELECT standard_price FROM product_product WHERE id = %s", (product_id,))[0]
			prices = row["standard_price"] or {}
			return float(prices.get(str(self.cid)) or 0.0)
		if self.old.has("ir_property"):
			row = self.old.rows("SELECT p.value_float FROM ir_property p JOIN ir_model_fields f ON f.id = p.fields_id "
				"WHERE f.name = 'standard_price' AND f.model = 'product.product' AND p.res_id = %s AND "
				"(p.company_id = %s OR p.company_id IS NULL) ORDER BY p.company_id NULLS LAST LIMIT 1",
				(f"product.product,{product_id}", self.cid))
			return float(row[0]["value_float"] or 0.0) if row else 0.0
		return 0.0

	def products(self):
		storable = self.old.column("product_template", "is_storable", "FALSE", "t")
		rows = self.old.rows(f"SELECT p.id, p.product_tmpl_id, p.default_code, p.barcode, p.active AS variant_active, t.name, "
			f"t.type, {storable}, t.list_price, t.sale_ok, t.purchase_ok, t.categ_id, t.uom_id, t.description_sale, "
			f"t.active, (SELECT count(*) FROM product_product v WHERE v.product_tmpl_id = t.id AND v.active) AS variants "
			f"FROM product_product p JOIN product_template t ON t.id = p.product_tmpl_id "
			f"WHERE (t.company_id IS NULL OR t.company_id = %s) AND t.active AND p.active ORDER BY p.id", (self.cid,))
		for row in rows:
			self.product(row["id"], row)
		say(f"  products: {self.counts['product']} new")

	def product(self, old_id, row=None):
		product = self.found("product.product", "product", old_id)
		if product:
			return product
		if row is None:
			storable = self.old.column("product_template", "is_storable", "FALSE", "t")
			found = self.old.rows(f"SELECT p.id, p.default_code, p.barcode, t.name, t.type, {storable}, t.list_price, "
				f"t.sale_ok, t.purchase_ok, t.categ_id, t.uom_id, t.description_sale, t.active, 1 AS variants "
				f"FROM product_product p JOIN product_template t ON t.id = p.product_tmpl_id WHERE p.id = %s", (old_id,))
			if not found:
				return self.env["product.product"]
			row = found[0]
		name = text(row["name"])
		if row["variants"] > 1:
			# A product with variants comes as one product per variant, its values in its name
			values = self.old.rows("SELECT v.name FROM product_variant_combination c JOIN product_template_attribute_value a "
				"ON a.id = c.product_template_attribute_value_id JOIN product_attribute_value v ON v.id = "
				"a.product_attribute_value_id WHERE c.product_product_id = %s ORDER BY v.id", (old_id,)) \
				if self.old.has("product_variant_combination") else []
			if values:
				name = "%s (%s)" % (name, ", ".join(text(v["name"]) for v in values))
		kind = row["type"]
		stored = row.get("is_storable") or kind == "product"
		kind = "consu" if kind in ("product", "consu") else "service" if kind == "service" else "consu"
		uom = self.uom(row["uom_id"])
		values = self.values("product.template", {"name": name, "type": kind, "list_price": row["list_price"] or 0.0,
			"sale_ok": row["sale_ok"], "purchase_ok": row["purchase_ok"], "categ_id": self.category(row["categ_id"]).id,
			"uom_id": uom.id, "description_sale": text(row["description_sale"]) or None,
			"default_code": row["default_code"], "active": row.get("active", True)})
		if "is_storable" in self.env["product.template"]._fields and kind == "consu":
			values["is_storable"] = bool(stored)
		barcode = row["barcode"]
		if barcode and self.env["product.product"].search_count([("barcode", "=", barcode)]):
			self.note(f"The barcode {barcode} of «{name}» is already used here; it was left out.")
			barcode = None
		template = self.env["product.template"].create(values)
		product = template.product_variant_id
		if barcode:
			product.barcode = barcode
		cost = self.standard_price(old_id)
		if cost:
			product.with_company(self.company).standard_price = cost
		return self.remember(product, "product", old_id)

	# accounts

	def old_accounts(self):
		"""{old id: (code, name, type, reconcile)} of the old company's accounts"""
		if self.old.has("account_account", "code_store"):
			rows = self.old.rows("SELECT id, code_store, name, account_type, reconcile FROM account_account")
			result = {}
			for row in rows:
				codes = row["code_store"] or {}
				code = codes.get(str(self.cid)) if isinstance(codes, dict) else None
				if code:
					result[row["id"]] = (code, text(row["name"]), row["account_type"], row["reconcile"])
			return result
		rows = self.old.rows("SELECT id, code, name, account_type, reconcile FROM account_account WHERE company_id = %s",
			(self.cid,))
		return {row["id"]: (row["code"], text(row["name"]), row["account_type"], row["reconcile"]) for row in rows}

	def account(self, old_id, accounts):
		account = self.found("account.account", "account", old_id)
		if account:
			return account
		code, name, kind, reconcile = accounts[old_id]
		Account = self.env["account.account"].with_company(self.company)
		account = Account.search([("code", "=", code)], limit=1)
		if account and account.account_type != kind:
			self.note(f"Account {code}: «{name}» was {kind} there and is «{account.name}» ({account.account_type}) "
				f"here; its balance went to the account here.")
		if not account:
			if kind == "equity_unaffected":
				account = Account.search([("account_type", "=", "equity_unaffected")], limit=1)
			elif kind in PARTNER_TYPES:
				# What customers owe and what is owed to vendors go to the accounts the contacts use here
				field = "property_account_receivable_id" if kind == "asset_receivable" else "property_account_payable_id"
				account = self.env["res.partner"].with_company(self.company).new({})[field]
				if account:
					self.note(f"Account {code} «{name}» is «{account.code} {account.name}» here, the account of contacts.")
			if not account:
				account = Account.create({"code": code, "name": name, "account_type": kind,
					"reconcile": bool(reconcile or kind in PARTNER_TYPES)})
				self.note(f"Account {code} «{name}» was added to the chart of accounts.")
		return self.remember(account, "account", old_id)

	def opening(self):
		"""One draft journal entry with the balances of the old company on the date: the accounts of the balance
		sheet from the start, the income and expenses of this fiscal year only, the years before in retained
		earnings"""
		accounts = self.old_accounts()
		start = self.company.compute_fiscalyear_dates(self.on)["date_from"]
		display = "AND (l.display_type IS NULL OR l.display_type NOT IN ('line_section', 'line_note'))" \
			if self.old.has("account_move_line", "display_type") else ""
		rows = self.old.rows(f"SELECT l.account_id, l.partner_id, a.account_type, sum(l.balance) AS balance, "
			f"sum(CASE WHEN l.date < %s THEN l.balance ELSE 0 END) AS before_year FROM account_move_line l "
			f"JOIN account_move m ON m.id = l.move_id JOIN account_account a ON a.id = l.account_id "
			f"WHERE m.state = 'posted' AND l.company_id = %s AND l.date <= %s {display} "
			f"GROUP BY l.account_id, l.partner_id, a.account_type", (start, self.cid, self.on))
		ref = OPENING_REF % (self.version, self.on.isoformat())
		Move = self.env["account.move"].with_company(self.company)
		twin = Move.search([("ref", "=", ref), ("company_id", "=", self.company.id)], limit=1)
		if twin and twin.state != "draft":
			say(f"  opening balances: already posted as {twin.name}; left as it is")
			return
		twin.unlink()
		totals = defaultdict(float)
		earlier = 0.0
		for row in rows:
			if row["account_id"] not in accounts:
				continue
			balance = float(row["balance"] or 0.0)
			if row["account_type"] in PROFIT_AND_LOSS:
				earlier += float(row["before_year"] or 0.0)
				balance -= float(row["before_year"] or 0.0)
			partner = row["partner_id"] if row["account_type"] in PARTNER_TYPES else None
			totals[(row["account_id"], partner)] += balance
		currency = self.company.currency_id
		lines = []
		for (account_id, partner_id), balance in sorted(totals.items(), key=lambda item: accounts[item[0][0]][0]):
			if currency.is_zero(balance):
				continue
			lines.append({"account_id": self.account(account_id, accounts).id, "partner_id": self.partner(partner_id).id or False,
				"name": accounts[account_id][1], "debit": balance if balance > 0 else 0.0, "credit": -balance if balance < 0 else 0.0})
		unaffected = self.env["account.account"].with_company(self.company).search(
			[("account_type", "=", "equity_unaffected")], limit=1)
		rest = -sum(line["debit"] - line["credit"] for line in lines)
		if not currency.is_zero(rest):
			if not currency.is_zero(rest - earlier):
				# The rows of balanced entries leave out only the income and expenses of the years before
				self.note("The old entries did not balance by %s; it is in retained earnings: check it." % f"{rest - earlier:,.0f}")
			lines.append({"account_id": unaffected.id, "name": "Profit and loss of the years before (Odoo %s)" % self.version,
				"debit": rest if rest > 0 else 0.0, "credit": -rest if rest < 0 else 0.0})
		if not lines:
			say("  opening balances: the old company has no posted entries up to this date")
			return
		journal = self.env["account.journal"].search([("type", "=", "general"), ("company_id", "=", self.company.id)], limit=1)
		move = Move.create({"move_type": "entry", "date": self.on, "ref": ref, "journal_id": journal.id,
			"line_ids": [(0, 0, line) for line in lines]})
		debit = sum(line["debit"] for line in lines)
		say(f"  opening balances: a DRAFT entry of {len(lines)} lines, {debit:,.0f} on each side, on {self.on} "
			f"(id {move.id}); an accountant checks it and posts it")

	# stock

	def stock(self):
		if "stock.quant" not in self.env or not self.old.has("stock_quant"):
			return
		rows = self.old.rows("SELECT q.product_id, sum(q.quantity) AS quantity FROM stock_quant q JOIN stock_location l "
			"ON l.id = q.location_id WHERE l.usage = 'internal' AND q.company_id = %s GROUP BY q.product_id "
			"HAVING sum(q.quantity) <> 0", (self.cid,))
		warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
		if not warehouse:
			return
		Quant = self.env["stock.quant"].with_context(inventory_mode=True)
		counted = 0
		for row in rows:
			product = self.product(row["product_id"])
			if not product or not product.is_storable:
				continue
			quant = Quant.search([("product_id", "=", product.id), ("location_id", "=", warehouse.lot_stock_id.id)], limit=1)
			if quant:
				quant.inventory_quantity = float(row["quantity"])
			else:
				Quant.create({"product_id": product.id, "location_id": warehouse.lot_stock_id.id,
					"inventory_quantity": float(row["quantity"])})
			counted += 1
		say(f"  stock: {counted} products counted in {warehouse.lot_stock_id.display_name}, NOT applied: in Inventory, "
			f"Physical Inventory, a person checks and presses Apply")

	# employees

	def employees(self):
		if "hr.employee" not in self.env or not self.old.has("hr_employee"):
			return
		name = "e.name" if self.old.has("hr_employee", "name") else "r.name"
		rows = self.old.rows(f"SELECT e.id, {name} AS name, e.job_title, e.work_phone, e.mobile_phone, e.work_email, "
			f"d.name AS department FROM hr_employee e JOIN resource_resource r ON r.id = e.resource_id LEFT JOIN "
			f"hr_department d ON d.id = e.department_id WHERE e.active AND e.company_id = %s", (self.cid,))
		for row in rows:
			if self.found("hr.employee", "employee", row["id"]):
				continue
			department = self.env["hr.department"]
			if row["department"]:
				department_name = text(row["department"])
				department = department.search([("name", "=", department_name), ("company_id", "=", self.company.id)],
					limit=1) or department.create({"name": department_name, "company_id": self.company.id})
			self.remember(self.env["hr.employee"].create(self.values("hr.employee", {"name": text(row["name"]),
				"job_title": row["job_title"], "work_phone": row["work_phone"], "mobile_phone": row["mobile_phone"],
				"work_email": row["work_email"], "department_id": department.id or None, "company_id": self.company.id})),
				"employee", row["id"])
		say(f"  employees: {self.counts['employee']} new")


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("backup")
	parser.add_argument("database")
	parser.add_argument("--date", help="the date of the opening balances, YYYY-MM-DD (Gregorian); today by default")
	parser.add_argument("--company", type=int, help="the number of the company in the backup, when it has several")
	parser.add_argument("--reload", action="store_true", help="load the backup anew into its own database")
	parser.add_argument("--check", action="store_true", help="only say what the backup has")
	args = parser.parse_args()

	import odoo
	from odoo.tools import config

	config.parse_config(["-c", "/etc/odoo/odoo.conf"])
	config["db_host"] = os.environ.get("HOST", "db")
	config["db_user"] = os.environ.get("USER", "odoo")
	config["db_password"] = os.environ.get("PASSWORD", "odoo")

	if not os.path.exists(args.backup):
		say("The backup is not found: %s" % args.backup)
		return 1
	backup = Backup(args.backup)
	try:
		manifest = backup.manifest()
	except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
		say("This is not a backup of the Odoo database manager (no manifest.json): %s" % error)
		return 1
	version = str(manifest.get("major_version") or manifest.get("version") or "?")
	edition = "Enterprise" if "e" in (manifest.get("version_info") or [])[-1:] else "Community"
	say(f"Backup of {manifest.get('db_name', '?')}: Odoo {version} {edition}, {len(manifest.get('modules') or {})} modules.")
	if not (version.startswith("17.") or version.startswith("18.")):
		say("This tool brings companies from Odoo 17 or 18. For %s, use «restore» when it is this program's version." % version)
		return 2

	import odoo.service.db as dbservice
	from odoo import SUPERUSER_ID, api
	from odoo.modules.registry import Registry

	if not dbservice.exp_db_exist(args.database):
		say(f"There is no database {args.database}. Make it first, with the programs of ERP-VERON:")
		say(f"  .\\odoo.ps1 createdb {args.database}")
		say(f"  .\\odoo.ps1 install veron_apps {args.database}")
		return 1
	on = date.fromisoformat(args.date) if args.date else date.today()
	dsn = load(backup, f"{args.database}_odoo18", reload=args.reload)
	old = Old(dsn)
	if args.check:
		for table, label in (("res_partner", "contacts"), ("product_product", "products"), ("account_account", "accounts"),
				("account_move", "journal entries"), ("stock_quant", "stock rows"), ("hr_employee", "employees")):
			if old.has(table):
				say(f"  {label}: {old.rows(f'SELECT count(*) AS n FROM {table}')[0]['n']}")
		return 0
	registry = Registry(args.database)
	with registry.cursor() as cr:
		env = api.Environment(cr, SUPERUSER_ID, {"lang": "fa_IR", "tracking_disable": True, "mail_create_nolog": True,
			"mail_notrack": True})
		if "account.move" not in env:
			say(f"Accounting is not installed in {args.database}: .\\odoo.ps1 install veron_apps {args.database}")
			return 1
		work = Import(env, old, backup, version, args.company, on)
		say(f"Bringing it into {args.database}:")
		work.company_details()
		work.partners()
		work.bank_accounts()
		work.products()
		work.employees()
		work.opening()
		work.stock()
		if work.notes:
			say("")
			say("To check:")
			for note in work.notes:
				say("  - " + note)
	say("")
	say("Done. Nothing was posted or applied: open the program and confirm it there:")
	say("  1. Accounting, Journal Entries: the draft «Opening balances from Odoo ...»: compare it with the trial")
	say("     balance of the old Odoo on the same date, then Post.")
	say("  2. Inventory, Physical Inventory: the counted quantities: check them, then Apply.")
	say(f"The old database stays as {args.database}_odoo18 for a second run; delete it in the database manager when done.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
