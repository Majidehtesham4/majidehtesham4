"""A company of Odoo 17 or 18 brought into this program with its history.

Every record is copied field by field: the fields both versions have, the relations turned into the records made
here, the translations kept. Each record made here is remembered by an external id (veron_import18.<model>__<company
of the backup>__<old id>), so a second run brings only what is new. Accounting entries come as drafts with their
old numbers and dates; posting them, reconciling and applying the stock is done in the program by a person, from
the record of the migration."""

import base64
import json
import logging
import re
from collections import defaultdict

from odoo import Command

from .source import text

_logger = logging.getLogger(__name__)

MODULE = "veron_import18"
MAGIC = {"id", "create_uid", "create_date", "write_uid", "write_date", "display_name", "__last_update"}
SKIP_PREFIX = ("message_", "activity_", "website_message", "rating_", "access_", "l10n_")
BATCH = 100
PROFIT_AND_LOSS = ("income", "income_other", "expense", "expense_depreciation", "expense_direct_cost")
PARTNER_TYPES = ("asset_receivable", "liability_payable")
# Fields whose name changed: {model: {field here: column there}}
RENAMED = {
	"sale.order.line": {"product_uom_id": "product_uom", "tax_ids": "tax_id"},
	"purchase.order.line": {"product_uom_id": "product_uom", "tax_ids": "taxes_id"},
	"product.supplierinfo": {"product_uom_id": "product_uom"},
}
# Fields never copied: worked out again here, or meaningful only in the old database
NEVER = {
	"account.move": {"state", "posted_before", "payment_state", "inalterable_hash", "secure_sequence_number",
		"statement_line_id", "origin_payment_id", "tax_cash_basis_rec_id", "tax_cash_basis_origin_move_id",
		"invoice_pdf_report_id", "auto_post_origin_id", "made_sequence_gap", "checked", "is_manually_modified"},
	"account.move.line": {"move_id", "full_reconcile_id", "reconciled", "amount_residual", "amount_residual_currency",
		"matching_number", "payment_id", "statement_line_id", "statement_id", "debit", "credit", "reconcile_model_id",
		"is_imported", "asset_id"},
	"account.payment": {"move_id", "is_reconciled", "is_matched", "attachment_ids"},
	"account.bank.statement.line": {"move_id", "is_reconciled"},
	"res.partner": {"user_id", "commercial_partner_id", "signup_type", "employee_ids"},
	"res.users": {"password", "totp_secret", "signature", "partner_id"},
	"sale.order": {"state", "invoice_ids", "transaction_ids", "procurement_group_id", "stock_reference_ids"},
	"sale.order.line": {"invoice_lines", "move_ids"},
	"purchase.order": {"state", "invoice_ids", "group_id"},
	"purchase.order.line": {"invoice_lines", "move_ids", "move_dest_ids"},
	"product.template": {"product_variant_ids", "attribute_line_ids", "uom_ids"},
	"product.product": {"product_tmpl_id", "product_template_attribute_value_ids", "product_template_variant_value_ids",
		"combination_indices"},
	"stock.move": {"product_qty"},
	"stock.quant": {"quantity", "reserved_quantity", "inventory_quantity_set", "user_id"},
	"hr.employee": {"user_id", "resource_id", "work_contact_id", "resource_calendar_id"},
	"account.journal": {"sequence_override_regex", "alias_id", "inbound_payment_method_line_ids",
		"outbound_payment_method_line_ids"},
}
# Fields worked out by this version that still take the old value: what was decided then stays
ALWAYS = {
	"account.payment": {"outstanding_account_id", "destination_account_id"},
}
# Kinds of journal entries of the old company that a person reconciles: their links are kept to be redone here
STOCK_USAGES = ("internal", "transit")


class Importer:
	def __init__(self, env, old, backup=None, version="18.0", company_id=None, say=print):
		self.env = env(context=dict(env.context, lang="en_US", active_test=False, tracking_disable=True,
			mail_create_nolog=True, mail_notrack=True, mail_auto_subscribe_no_notify=True, no_reset_password=True,
			skip_invoice_sync=True, check_move_validity=False, skip_account_move_synchronization=True,
			mail_notify_force_send=False, install_mode=True))
		self.old, self.backup, self.version, self.say = old, backup, version, say
		self.company = self.env.company
		companies = old.rows("SELECT id, name FROM res_company ORDER BY id")
		if len(companies) > 1:
			say("The backup has %s companies: %s" % (len(companies), ", ".join(f"{c['id']}: {c['name']}" for c in companies)))
		self.old_company = next((c for c in companies if c["id"] == company_id), companies[0])
		self.cid = self.old_company["id"]
		self.counts = defaultdict(int)
		self.failed = defaultdict(int)
		self.notes = []
		self.map = defaultdict(dict)
		self.pending = []
		self.relations = {}
		self.old_fields = {}
		self.properties = {}
		self.move_states = {}
		self.groups = []
		self.made_taxes = set()
		self.payment_states = {}
		self.langs = {code for code, _name in self.env["res.lang"].get_installed()}
		self._load_map()

	# --- notes

	def note(self, message):
		if message not in self.notes:
			self.notes.append(message)

	# --- where each old record went

	def _xmlid(self, model, old_id):
		return f"{model.replace('.', '_')}__{self.cid}__{old_id}"

	def _load_map(self):
		self.env.cr.execute("SELECT model, name, res_id FROM ir_model_data WHERE module = %s AND name LIKE %s",
			(MODULE, f"%\\_\\_{self.cid}\\_\\_%"))
		found = defaultdict(dict)
		for model, name, res_id in self.env.cr.fetchall():
			found[model][int(name.rsplit("__", 1)[1])] = res_id
		for model, ids in found.items():
			if model not in self.env:
				continue
			alive = set(self.env[model].browse(list(ids.values())).exists().ids)
			self.map[model] = {old: new for old, new in ids.items() if new in alive}

	def remember(self, model, old_id, new_id):
		self.map[model][old_id] = new_id
		self.pending.append((self._xmlid(model, old_id), model, new_id))

	def flush(self):
		"""The external ids of the records made, written in one statement per thousand"""
		for start in range(0, len(self.pending), 1000):
			chunk = self.pending[start:start + 1000]
			self.env.cr.execute(
				"INSERT INTO ir_model_data (module, name, model, res_id, noupdate, create_date, write_date, create_uid, "
				"write_uid) VALUES " + ", ".join(["(%s, %s, %s, %s, true, now(), now(), 1, 1)"] * len(chunk)) +
				" ON CONFLICT (module, name) DO UPDATE SET res_id = EXCLUDED.res_id",
				[value for name, model, res_id in chunk for value in (MODULE, name, model, res_id)])
		self.pending = []

	def new(self, model, old_id):
		"""The record here for a record of the old database, or an empty one"""
		Model = self.env[model] if model in self.env else None
		if Model is None or not old_id:
			return self.env["res.partner"].browse() if Model is None else Model
		return Model.browse(self.target(model, old_id) or [])

	# --- values of the old database turned into values here

	def old_relation(self, model, field):
		"""The table and columns of a many2many of the old database, by the field's name there"""
		key = (model, field.name)
		if key in self.old_fields:
			return self.old_fields[key]
		name = RENAMED.get(model, {}).get(field.name, field.name)
		result = None
		if self.old.has("ir_model_fields", "relation_table"):
			rows = self.old.rows("SELECT relation_table, column1, column2 FROM ir_model_fields WHERE model = %s AND "
				"name = %s AND ttype = 'many2many'", (model, name))
			if rows and rows[0]["relation_table"]:
				result = (rows[0]["relation_table"], rows[0]["column1"], rows[0]["column2"])
		if not result and self.old.has(field.relation, field.column1):
			result = (field.relation, field.column1, field.column2)
		self.old_fields[key] = result
		return result

	def pairs(self, table, column1, column2):
		key = (table, column1, column2)
		if key not in self.relations:
			found = defaultdict(list)
			if self.old.has(table, column1) and self.old.has(table, column2):
				for row in self.old.rows(f'SELECT "{column1}" AS a, "{column2}" AS b FROM "{table}"'):
					found[row["a"]].append(row["b"])
			self.relations[key] = found
		return self.relations[key]

	def property(self, model, field, old_id):
		"""A company-dependent value of Odoo 17 and before, kept in ir_property"""
		key = (model, field)
		if key not in self.properties:
			values = {}
			if self.old.has("ir_property"):
				rows = self.old.rows("SELECT p.res_id, p.value_reference, p.value_float, p.value_integer, p.value_text, "
					"p.value_datetime FROM ir_property p JOIN ir_model_fields f ON f.id = p.fields_id WHERE f.model = %s "
					"AND f.name = %s AND (p.company_id = %s OR p.company_id IS NULL) ORDER BY p.company_id NULLS FIRST",
					(model, field, self.cid))
				for row in rows:
					value = row["value_reference"] or row["value_float"] or row["value_integer"] or row["value_text"] or \
						row["value_datetime"]
					if isinstance(value, str) and "," in value and row["value_reference"]:
						value = int(value.split(",")[1])
					values[row["res_id"]] = value
			self.properties[key] = values
		return self.properties[key].get(f"{model},{old_id}", self.properties[key].get(None))

	def target(self, comodel, old_id):
		"""The id here of a record a relation of the old database points to; None when it is not brought"""
		if not old_id:
			return None
		if comodel == "res.company":
			return self.company.id
		if comodel in self.map and old_id in self.map[comodel]:
			return self.map[comodel][old_id]
		lookup = getattr(self, "_lookup_" + comodel.replace(".", "_"), None)
		record = lookup(old_id) if lookup else None
		if not record and self.old.has("ir_model_data"):
			# A record a module brought with it (a unit, a stage, a kind of loss...) is the same record here
			record = self._lookup_by_xmlid(comodel, old_id)
		if record:
			self.map[comodel][old_id] = record.id
			return record.id
		return None

	def _lookup_res_currency(self, old_id):
		name = self.old.value("SELECT name FROM res_currency WHERE id = %s", (old_id,))
		currency = self.env["res.currency"].search([("name", "=", name)], limit=1) if name else None
		if currency and not currency.active:
			currency.active = True
		return currency

	def _lookup_res_country(self, old_id):
		code = self.old.value("SELECT code FROM res_country WHERE id = %s", (old_id,))
		return self.env["res.country"].search([("code", "=", code)], limit=1) if code else None

	def _lookup_res_country_state(self, old_id):
		row = self.old.rows("SELECT s.code, c.code AS country FROM res_country_state s JOIN res_country c ON "
			"c.id = s.country_id WHERE s.id = %s", (old_id,))
		if not row:
			return None
		return self.env["res.country.state"].search([("code", "=", row[0]["code"]),
			("country_id.code", "=", row[0]["country"])], limit=1)

	def _lookup_by_xmlid(self, model, old_id):
		row = self.old.rows("SELECT module, name FROM ir_model_data WHERE model = %s AND res_id = %s AND module != %s "
			"LIMIT 1", (model, old_id, MODULE))
		if not row:
			return None
		record = self.env.ref(f"{row[0]['module']}.{row[0]['name']}", raise_if_not_found=False)
		return record if record and record._name == model else None

	def _lookup_res_groups(self, old_id):
		return self._lookup_by_xmlid("res.groups", old_id)

	def _lookup_mail_message_subtype(self, old_id):
		return self._lookup_by_xmlid("mail.message.subtype", old_id)

	def _lookup_account_payment_method(self, old_id):
		row = self.old.rows("SELECT code, payment_type FROM account_payment_method WHERE id = %s", (old_id,))
		if not row:
			return None
		return self.env["account.payment.method"].search([("code", "=", row[0]["code"]),
			("payment_type", "=", row[0]["payment_type"])], limit=1)

	def _lookup_res_users(self, old_id):
		login = self.old.value("SELECT login FROM res_users WHERE id = %s", (old_id,))
		return self.env["res.users"].search([("login", "=", login)], limit=1) if login else None

	def _lookup_stock_location(self, old_id):
		row = self.old.rows("SELECT usage FROM stock_location WHERE id = %s", (old_id,))
		if not row or row[0]["usage"] in STOCK_USAGES or row[0]["usage"] == "view":
			return None
		# The locations of partners and of inventory are the same everywhere
		usage = row[0]["usage"]
		xmlid = {"customer": "stock.stock_location_customers", "supplier": "stock.stock_location_suppliers",
			"inventory": "stock.stock_location_inventory" if self.env.ref("stock.stock_location_inventory",
			raise_if_not_found=False) else None, "production": None}.get(usage)
		if xmlid:
			return self.env.ref(xmlid, raise_if_not_found=False)
		return self.env["stock.location"].search([("usage", "=", usage), ("company_id", "in", [self.company.id, False])],
			limit=1)

	def named(self, model, row, domain=(), field="name"):
		"""The record here with the name of the old row, in any of its languages"""
		raw = row.get(field)
		names = raw if isinstance(raw, dict) else {"en_US": raw}
		values = [value for value in dict.fromkeys(names.values()) if value]
		Model = self.env[model]
		for lang in dict.fromkeys(["en_US"] + [lang for lang in names if lang in self.langs]):
			found = Model.with_context(lang=lang).search([(field, "in", values)] + list(domain), limit=1)
			if found:
				return found.with_context(lang="en_US")
		return Model

	def convert(self, model, row, table=None, skip=(), only=None):
		"""The values of a record here from a row of the old database: (values, translations, references to the
		model itself, to set once every record exists)"""
		Model = self.env[model]
		table = table or Model._table
		columns = self.old.columns(table)
		renamed = RENAMED.get(model, {})
		never = NEVER.get(model, set())
		values, translations, later = {}, {}, {}
		for name, field in Model._fields.items():
			if only is not None and name not in only:
				continue
			if name in MAGIC or name in skip or name in never or name.startswith(SKIP_PREFIX):
				continue
			# Fields of a delegated model (the version of an employee) are written through the record
			inherited = getattr(field, "inherited", False)
			# A stored related field that can be written (the name of a work center, kept on its resource) is copied
			if not inherited and (not field.store or field.related and field.readonly) or field.type in ("one2many", "binary", "properties",
					"properties_definition", "reference", "many2one_reference"):
				continue
			if field.compute and field.readonly and not field.company_dependent and not inherited and \
					name not in ALWAYS.get(model, ()):
				continue
			column = renamed.get(name, name)
			if field.type == "many2many":
				relation = self.old_relation(model, field)
				if relation and "id" in row and field.comodel_name in self.env:
					old_ids = self.pairs(*relation).get(row["id"], [])
					new_ids = [i for i in (self.target(field.comodel_name, o) for o in old_ids) if i]
					if new_ids:
						values[name] = [Command.set(new_ids)]
				continue
			if column in columns:
				raw = row.get(column)
			elif inherited and field.related:
				# Kept on the delegated record in the old database too (the resource of a work center)
				raw = self.parent_value(Model, field, row)
				if raw is None:
					continue
			elif field.company_dependent and "id" in row:
				raw = self.property(model, name, row["id"])
			else:
				continue
			if field.company_dependent and isinstance(raw, dict):
				raw = raw.get(str(self.cid))
			if raw is None or raw == "":
				continue
			if field.type == "many2one":
				if field.comodel_name not in self.env:
					continue
				if field.comodel_name == model and field.comodel_name != "res.users":
					later[name] = raw
					continue
				new_id = self.target(field.comodel_name, raw)
				if new_id:
					values[name] = new_id
			elif field.type == "selection":
				try:
					valid = [key for key, _label in field._description_selection(self.env)]
				except Exception:  # noqa: BLE001 - a selection worked out from records that are not here
					valid = []
				if raw in valid:
					values[name] = raw
			elif field.type in ("char", "text", "html"):
				if isinstance(raw, dict) or (isinstance(raw, str) and raw.startswith("{") and columns.get(column) == "jsonb"):
					raw = json.loads(raw) if isinstance(raw, str) else raw
					if field.translate and not callable(field.translate):
						values[name] = raw.get("en_US") or text(raw)
						translations[name] = {lang: value for lang, value in raw.items() if lang in self.langs and
							lang != "en_US" and value}
					else:
						values[name] = text(raw)
				else:
					values[name] = raw
			elif field.type in ("float", "monetary"):
				values[name] = float(raw)
			elif field.type == "integer":
				values[name] = int(raw)
			elif field.type == "json":
				values[name] = self.distribution(raw) if name == "analytic_distribution" else raw
			else:
				values[name] = raw
		return values, translations, later

	def parent_value(self, Model, field, row):
		link, name = field.related.split(".", 1) if isinstance(field.related, str) else (field.related[0], field.related[1])
		parent = Model._fields[link].comodel_name if link in Model._fields else None
		if not parent or not row.get(link) or "." in name:
			return None
		table = self.env[parent]._table
		key = (table, row[link])
		if key not in self.relations:
			found = self.old.rows(f'SELECT * FROM "{table}" WHERE id = %s', (row[link],)) if self.old.has(table) else []
			self.relations[key] = found[0] if found else {}
		return self.relations[key].get(name)

	def distribution(self, raw):
		"""An analytic distribution with the analytic accounts of here"""
		raw = json.loads(raw) if isinstance(raw, str) else raw
		result = {}
		for key, percent in (raw or {}).items():
			ids = [self.target("account.analytic.account", int(part)) for part in str(key).split(",") if part.isdigit()]
			if ids and all(ids):
				result[",".join(map(str, ids))] = percent
		return result or None

	def translate(self, record, translations):
		for name, by_lang in translations.items():
			for lang, value in by_lang.items():
				record.with_context(lang=lang)[name] = value

	def copy(self, model, rows, match=None, skip=(), extra=None, table=None, label=None):
		"""A record here for each row not yet brought: found by match, or made from the row"""
		if model not in self.env:
			if rows:
				self.note(f"{len(rows)} records of {model} were not brought: that part of the program is not installed here.")
			return
		Model = self.env[model]
		made, deferred = [], []
		for start in range(0, len(rows), BATCH):
			chunk = [row for row in rows[start:start + BATCH] if row["id"] not in self.map[model]]
			todo = []
			for row in chunk:
				found = match(row) if match else None
				if found:
					self.remember(model, row["id"], found.id)
					continue
				values, translations, later = self.convert(model, row, table, skip)
				if extra:
					values.update(extra(row, values) or {})
				todo.append((row, values, translations, later))
			if not todo:
				continue
			try:
				with self.env.cr.savepoint():
					records = Model.create([values for _row, values, _t, _l in todo])
			except Exception:  # noqa: BLE001 - one bad row does not stop the others: they are made one by one
				records = None
			if records is None:
				records = Model.browse()
				for row, values, translations, later in todo:
					try:
						with self.env.cr.savepoint():
							records |= Model.create(values)
					except Exception as error:  # noqa: BLE001 - counted and shown at the end
						self.failed[model] += 1
						_logger.warning("%s %s was not brought: %s", model, row["id"], error)
						if self.failed[model] <= 3:
							self.note(f"{model} {row['id']} ({row.get('name') or row.get('display_name') or ''}) was not "
								f"brought: {str(error).splitlines()[0][:200]}")
						todo = [item for item in todo if item[0] is not row]
			for (row, _values, translations, later), record in zip(todo, records):
				self.remember(model, row["id"], record.id)
				if translations:
					self.translate(record, translations)
				if later:
					deferred.append((record, later))
				made.append(record.id)
			self.flush()
		for record, later in deferred:
			values = {name: self.target(model, old_id) for name, old_id in later.items()}
			values = {name: value for name, value in values.items() if value}
			if values:
				try:
					with self.env.cr.savepoint():
						record.write(values)
				except Exception as error:  # noqa: BLE001
					_logger.warning("%s %s: %s", model, record.id, error)
		self.counts[label or model] += len(made)
		return Model.browse(made)

	def rows(self, table, where="", params=(), order="id"):
		"""The rows of a table of the old database for the old company: its own and the shared ones"""
		if not self.old.has(table):
			return []
		conditions = [where] if where else []
		if self.old.has(table, "company_id") and "company_id" not in where:
			conditions.append(f"(company_id IS NULL OR company_id = {int(self.cid)})")
		clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
		return self.old.rows(f'SELECT * FROM "{table}"{clause} ORDER BY {order}', params)

	# --- the steps

	def steps(self):
		return [self.custom_fields, self.company_details, self.currencies, self.users, self.analytic, self.accounts,
			self.taxes, self.journals, self.payment_terms, self.fiscal_positions, self.partners, self.banks, self.uoms,
			self.products, self.pricelists, self.hr, self.warehouses, self.orders, self.extras, self.pickings, self.moves,
			self.payments,
			self.statements, self.reconciliations, self.stock, self.attachments, self.messages]

	def run(self):
		for step in self.steps():
			self.say(f"  {step.__name__.replace('_', ' ')}...")
			step()
			self.flush()
			self.env.flush_all()
		return self

	def custom_fields(self):
		"""Fields added in the old database by Studio or by hand (x_...), made here on the models brought"""
		if not self.old.has("ir_model_fields", "state"):
			return
		rows = self.old.rows("SELECT * FROM ir_model_fields WHERE state = 'manual' AND name LIKE 'x\\_%%' ORDER BY id")
		Fields = self.env["ir.model.fields"].sudo()
		simple = ("char", "text", "html", "integer", "float", "monetary", "boolean", "date", "datetime", "selection",
			"many2one")
		for row in rows:
			model = self.env["ir.model"].sudo().search([("model", "=", row["model"])], limit=1)
			if not model or row["name"] in self.env[row["model"]]._fields or re.match(r"x_plan\d+_id$", row["name"]):
				# The columns of analytic plans are made by the plans themselves
				continue
			kind = row["ttype"]
			if kind not in simple or kind == "many2one" and (row["relation"] not in self.env):
				self.note(f"The field {row['model']}.{row['name']} ({kind}) was not made here.")
				continue
			if kind == "monetary":
				kind = "float"
			values = {"model_id": model.id, "name": row["name"], "ttype": kind, "state": "manual",
				"field_description": text(row["field_description"]) or row["name"], "relation": row.get("relation")
				if kind == "many2one" else False, "translate": bool(row.get("translate")) if kind in ("char", "text", "html")
				else False}
			if kind == "selection" and self.old.has("ir_model_fields_selection"):
				options = self.old.rows("SELECT value, name FROM ir_model_fields_selection WHERE field_id = %s ORDER BY "
					"sequence, id", (row["id"],))
				values["selection_ids"] = [Command.create({"value": o["value"], "name": text(o["name"]) or o["value"],
					"sequence": i}) for i, o in enumerate(options)]
			try:
				with self.env.cr.savepoint():
					Fields.create(values)
				self.counts["custom fields"] += 1
			except Exception as error:  # noqa: BLE001
				self.note(f"The field {row['model']}.{row['name']} was not made here: {str(error).splitlines()[0][:150]}")

	def company_details(self):
		row = self.old.rows("SELECT c.partner_id, c.currency_id, p.* FROM res_company c JOIN res_partner p ON "
			"p.id = c.partner_id WHERE c.id = %s", (self.cid,))[0]
		values, translations, _later = self.convert("res.partner", row, only={"name", "street", "street2", "city", "zip",
			"phone", "email", "website", "vat", "company_registry", "country_id", "state_id"})
		values.pop("company_id", None)
		if values.get("name") and self.env["res.company"].search_count([("name", "=", values["name"]),
				("id", "!=", self.company.id)]):
			self.note(f"Another company here is named «{values.pop('name')}»; this one keeps its name.")
		self.company.write({key: value for key, value in values.items() if key in self.company._fields})
		logo = self.image("res.partner", "image_1920", row["partner_id"])
		if logo:
			self.company.logo = logo
		self.remember("res.partner", row["partner_id"], self.company.partner_id.id)
		currency = self.old.value("SELECT name FROM res_currency WHERE id = %s", (row["currency_id"],))
		if currency != self.company.currency_id.name:
			self.note(f"The old company kept its accounts in {currency}, this one in {self.company.currency_id.name}: "
				f"the amounts are brought as they are.")

	def currencies(self):
		"""The exchange rates of the old company"""
		if "res.currency.rate" not in self.env or not self.old.has("res_currency_rate"):
			return
		Rate = self.env["res.currency.rate"]
		rows = self.rows("res_currency_rate")
		for row in rows:
			currency = self.target("res.currency", row["currency_id"])
			if not currency or row["id"] in self.map["res.currency.rate"]:
				continue
			if Rate.search_count([("currency_id", "=", currency), ("name", "=", row["name"]),
					("company_id", "in", [self.company.id, False])]):
				continue
			record = Rate.create({"currency_id": currency, "name": row["name"], "rate": float(row["rate"]),
				"company_id": self.company.id})
			self.remember("res.currency.rate", row["id"], record.id)
			self.counts["exchange rates"] += 1

	def users(self):
		"""The people who worked in the old system, ARCHIVED and without their passwords: an administrator here
		checks each one, gives access and sends the invitation"""
		share = "AND u.share IS NOT TRUE" if self.old.has("res_users", "share") else ""
		rows = self.old.rows(f"SELECT u.*, p.name, p.email, p.phone FROM res_users u JOIN res_partner p ON p.id = "
			f"u.partner_id WHERE u.login NOT IN ('__system__', 'public', 'portaltemplate', 'default') {share} ORDER BY u.id")
		Users = self.env["res.users"].with_context(no_reset_password=True)
		groups_field = "group_ids" if "group_ids" in Users._fields else "groups_id"
		group_table = "res_groups_users_rel"
		members = self.pairs(group_table, "uid", "gid") if self.old.has(group_table) else {}
		for row in rows:
			if row["id"] in self.map["res.users"]:
				continue
			user = Users.search([("login", "=", row["login"])], limit=1)
			if not user:
				groups = [g for g in (self.target("res.groups", gid) for gid in members.get(row["id"], [])) if g]
				values = {"name": row["name"] or row["login"], "login": row["login"], "email": row["email"],
					"active": False, "company_id": self.company.id, "company_ids": [Command.set(self.company.ids)]}
				if groups:
					values[groups_field] = [Command.set(groups)]
				try:
					with self.env.cr.savepoint():
						user = Users.create(values)
				except Exception as error:  # noqa: BLE001
					try:
						with self.env.cr.savepoint():
							values.pop(groups_field, None)
							user = Users.create(values)
					except Exception:  # noqa: BLE001
						self.note(f"The user {row['login']} was not made: {str(error).splitlines()[0][:150]}")
						continue
				self.counts["users (archived)"] += 1
			self.remember("res.users", row["id"], user.id)
			self.remember("res.partner", row["partner_id"], user.partner_id.id)

	def analytic(self):
		Plan = "account.analytic.plan"
		self.copy(Plan, self.rows("account_analytic_plan"), match=lambda row: self.named(Plan, row))
		self.copy("account.analytic.account", self.rows("account_analytic_account"))

	def old_codes(self):
		"""{old account id: code} of the old company's accounts"""
		if self.old.has("account_account", "code_store"):
			rows = self.old.rows("SELECT id, code_store FROM account_account")
			return {row["id"]: (row["code_store"] or {}).get(str(self.cid)) for row in rows
				if isinstance(row["code_store"], dict) and (row["code_store"] or {}).get(str(self.cid))}
		rows = self.old.rows("SELECT id, code FROM account_account WHERE company_id = %s", (self.cid,))
		return {row["id"]: row["code"] for row in rows}

	def accounts(self):
		# Tags (tax grids) first: accounts, taxes and entries point to them
		self.copy("account.account.tag", self.rows("account_account_tag"), match=lambda row: self.named(
			"account.account.tag", row, [("applicability", "=", row["applicability"])]))
		codes = self.old_codes()
		Account = self.env["account.account"].with_company(self.company)
		rows = [row for row in self.rows("account_account") if row["id"] in codes]

		def match(row):
			code = codes[row["id"]]
			account = Account.search([("code", "=", code)], limit=1)
			if account and account.account_type != row["account_type"]:
				self.note(f"Account {code} «{text(row['name'])}» was {row['account_type']} there and is «{account.name}» "
					f"({account.account_type}) here; its entries went to the account here.")
			if not account and row["account_type"] == "equity_unaffected":
				account = Account.search([("account_type", "=", "equity_unaffected")], limit=1)
			if not account and row["account_type"] in PARTNER_TYPES:
				field = "property_account_receivable_id" if row["account_type"] == "asset_receivable" else \
					"property_account_payable_id"
				account = self.env["res.partner"].with_company(self.company).new({})[field]
				if account:
					self.note(f"Account {code} «{text(row['name'])}» is «{account.code} {account.name}» here, the "
						f"account of contacts.")
			return account

		def extra(row, values):
			values["code"] = codes[row["id"]]
			if "active" in Account._fields and "deprecated" in row:
				values["active"] = not row["deprecated"]
			if row["account_type"] in PARTNER_TYPES:
				values["reconcile"] = True
			return values

		made = self.copy("account.account", rows, match=match, extra=extra, skip={"code_store", "company_ids"})
		for account in made or []:
			self.note(f"Account {account.code} «{account.name}» was added to the chart of accounts.")

	def taxes(self):
		self.copy("account.tax.group", self.rows("account_tax_group"), match=lambda row: self.named(
			"account.tax.group", row, [("company_id", "=", self.company.id)]))
		Tax = self.env["account.tax"]
		rows = self.rows("account_tax")

		def match(row):
			return self.named("account.tax", row, [("type_tax_use", "=", row["type_tax_use"]),
				("company_id", "=", self.company.id)]) or Tax.search([("type_tax_use", "=", row["type_tax_use"]),
				("amount_type", "=", row["amount_type"]), ("amount", "=", float(row["amount"])),
				("company_id", "=", self.company.id)], limit=1)

		made = self.copy("account.tax", rows, match=match, skip={"invoice_repartition_line_ids",
			"refund_repartition_line_ids", "repartition_line_ids"})
		self.made_taxes = set(made.ids) if made else set()
		# Each repartition line of the old taxes to the line here of the same kind, in the same order
		old_lines = defaultdict(list)
		for line in self.old.rows("SELECT * FROM account_tax_repartition_line ORDER BY sequence, id"):
			old_lines[(line["tax_id"], line["document_type"], line["repartition_type"])].append(line)
		for (old_tax, document, kind), lines in old_lines.items():
			tax = self.new("account.tax", old_tax)
			if not tax:
				continue
			here = tax.repartition_line_ids.filtered(lambda l: l.document_type == document and l.repartition_type == kind)
			here = here.sorted(lambda l: (l.sequence, l.id))
			for index, line in enumerate(lines):
				if index < len(here):
					self.remember("account.tax.repartition.line", line["id"], here[index].id)
					if tax.id in self.made_taxes:
						# A tax made here: its lines take the accounts, grids and shares of the old ones
						values, _t, _l = self.convert("account.tax.repartition.line", line, skip={"tax_id", "company_id"})
						with self.env.cr.savepoint():
							here[index].write(values)
				elif line["account_id"] or line["factor_percent"]:
					values, _t, _l = self.convert("account.tax.repartition.line", line)
					values.update({"tax_id": tax.id})
					with self.env.cr.savepoint():
						record = self.env["account.tax.repartition.line"].create(values)
					self.remember("account.tax.repartition.line", line["id"], record.id)

	def journals(self):
		Journal = self.env["account.journal"]
		def match(row):
			found = Journal.search([("code", "=", row["code"]), ("company_id", "=", self.company.id)], limit=1)
			if not found and row["type"] in ("sale", "purchase", "general") and self._only_journal(row):
				# The single sales (purchase, miscellaneous) journal of the old company is the one here
				found = Journal.search([("type", "=", row["type"]), ("company_id", "=", self.company.id)], limit=1)
			return found

		self.copy("account.journal", self.rows("account_journal"), match=match)
		# Payment methods of each journal
		if self.old.has("account_payment_method_line"):
			for row in self.old.rows("SELECT * FROM account_payment_method_line ORDER BY id"):
				journal = self.new("account.journal", row["journal_id"])
				method = self.target("account.payment.method", row["payment_method_id"])
				if not journal or not method or row["id"] in self.map["account.payment.method.line"]:
					continue
				line = self.env["account.payment.method.line"].search([("journal_id", "=", journal.id),
					("payment_method_id", "=", method)], limit=1)
				if not line:
					values, _t, _l = self.convert("account.payment.method.line", row)
					try:
						with self.env.cr.savepoint():
							line = self.env["account.payment.method.line"].create(values)
					except Exception:  # noqa: BLE001
						continue
				self.remember("account.payment.method.line", row["id"], line.id)

	def _only_journal(self, row):
		"""Whether the old company has a single journal of this type: then it is the journal of that type here"""
		return self.old.value("SELECT count(*) FROM account_journal WHERE type = %s AND company_id = %s",
			(row["type"], self.cid)) == 1

	def payment_terms(self):
		Term = self.env["account.payment.term"]
		lines = defaultdict(list)
		for line in self.rows("account_payment_term_line"):
			lines[line["payment_id"]].append(line)

		def extra(row, values):
			# The lines of the term as they were, in place of the line a new term gets by default
			made = [self.convert("account.payment.term.line", line, skip={"payment_id"})[0] for line in lines[row["id"]]]
			if made:
				values["line_ids"] = [Command.clear()] + [Command.create(line) for line in made]
			return values

		self.copy("account.payment.term", self.rows("account_payment_term"), match=lambda row: self.named(
			"account.payment.term", row, [("company_id", "in", [self.company.id, False])]), skip={"line_ids"}, extra=extra)

	def fiscal_positions(self):
		self.copy("account.fiscal.position", self.rows("account_fiscal_position"), match=lambda row: self.named(
			"account.fiscal.position", row, [("company_id", "=", self.company.id)]), skip={"tax_ids", "account_ids"})
		self.copy("account.fiscal.position.account", self.rows("account_fiscal_position_account"))
		if "account.fiscal.position.tax" in self.env:
			self.copy("account.fiscal.position.tax", self.rows("account_fiscal_position_tax"))
		elif self.old.has("account_fiscal_position_tax") and self.old.value("SELECT count(*) FROM account_fiscal_position_tax"):
			self.note("The tax mappings of fiscal positions are set on the taxes in this version: check them in "
				"Accounting settings.")

	def partners(self):
		self.copy("res.partner.category", self.rows("res_partner_category"), match=lambda row: self.named(
			"res.partner.category", row))
		if self.old.has("res_partner_industry"):
			self.copy("res.partner.industry", self.rows("res_partner_industry"), match=lambda row: self.named(
				"res.partner.industry", row))
		# Companies first, then the people and addresses under them
		rows = self.rows("res_partner", "id NOT IN (SELECT partner_id FROM res_company WHERE partner_id IS NOT NULL) AND "
			"id NOT IN (SELECT partner_id FROM res_users WHERE login IN ('__system__', 'public', 'portaltemplate', "
			"'default') AND partner_id IS NOT NULL)", order="parent_id NULLS FIRST, id")

		def extra(row, values):
			if row.get("mobile") and "mobile" not in self.env["res.partner"]._fields:
				# One phone number on a contact in this version: the mobile goes there when the phone is empty
				values["phone"] = values.get("phone") or row["mobile"]
			if not values.get("name") and not row.get("parent_id"):
				values["name"] = row.get("display_name") or row.get("email") or "-"
			return values

		self.copy("res.partner", rows, extra=extra, label="contacts")
		self.images("res.partner")

	def banks(self):
		self.copy("res.bank", self.rows("res_bank"), match=lambda row: self.env["res.bank"].search(
			["|", ("name", "=", row["name"]), ("bic", "=", row.get("bic") or "-")], limit=1))
		Bank = self.env["res.partner.bank"]
		self.copy("res.partner.bank", self.rows("res_partner_bank"), match=lambda row: Bank.search(
			[("acc_number", "=", row["acc_number"]), ("partner_id", "=", self.target("res.partner", row["partner_id"]))],
			limit=1), label="bank accounts")

	def uoms(self):
		Uom = self.env["uom.uom"]
		rows = self.rows("uom_uom", order="id")
		references = {}
		if self.old.has("uom_uom", "uom_type"):
			references = {row["category_id"]: row["id"] for row in rows if row["uom_type"] == "reference"}

		def match(row):
			names = row["name"] if isinstance(row["name"], dict) else {"en_US": row["name"]}
			for name in [names.get("en_US")] + list(names.values()):
				found = Uom.search([("name", "=ilike", name)], limit=1) if name else None
				if found:
					return found
			return None

		def extra(row, values):
			if "relative_uom_id" in Uom._fields and row.get("uom_type") and row["uom_type"] != "reference":
				reference = references.get(row.get("category_id"))
				if reference and self.target("uom.uom", reference):
					values["relative_uom_id"] = self.target("uom.uom", reference)
					values["relative_factor"] = 1.0 / float(row["factor"] or 1.0)
			return values

		ordered = sorted(rows, key=lambda row: 0 if row.get("uom_type") == "reference" else 1)
		self.copy("uom.uom", ordered, match=match, extra=extra, skip={"factor", "category_id"})

	def products(self):
		Category = self.env["product.category"]
		self.copy("product.category", self.rows("product_category", order="parent_id NULLS FIRST, id"),
			match=lambda row: Category.search([("name", "=", row["name"]), ("parent_id", "=", self.target(
			"product.category", row["parent_id"]) or False)], limit=1))
		Attribute, Value = self.env["product.attribute"], self.env["product.attribute.value"]
		self.copy("product.attribute", self.rows("product_attribute"), match=lambda row: self.named(
			"product.attribute", row))
		self.copy("product.attribute.value", self.rows("product_attribute_value"), match=lambda row: self.named(
			"product.attribute.value", row, [("attribute_id", "=", self.target("product.attribute", row["attribute_id"]))]))
		self.copy("product.tag", self.rows("product_tag"), match=lambda row: self.named("product.tag", row)) if "product.tag" in self.env else None
		def extra(row, values):
			if row.get("type") == "product":
				# Odoo 17: a stored product is a goods product kept in stock
				values.update({"type": "consu", "is_storable": True})
			return values

		self.copy("product.template", self.rows("product_template"), extra=extra, label="products")
		# The attributes of each product: its variants are made here from them and found by their values
		for row in self.rows("product_template_attribute_line"):
			if row["id"] in self.map["product.template.attribute.line"]:
				continue
			template = self.new("product.template", row["product_tmpl_id"])
			attribute = self.target("product.attribute", row["attribute_id"])
			value_ids = [self.target("product.attribute.value", v) for v in self.pairs(
				"product_attribute_value_product_template_attribute_line_rel", "product_template_attribute_line_id",
				"product_attribute_value_id").get(row["id"], [])]
			value_ids = [v for v in value_ids if v]
			if not template or not attribute or not value_ids:
				continue
			line = template.attribute_line_ids.filtered(lambda l: l.attribute_id.id == attribute)
			if not line:
				line = self.env["product.template.attribute.line"].create({"product_tmpl_id": template.id,
					"attribute_id": attribute, "value_ids": [Command.set(value_ids)]})
			self.remember("product.template.attribute.line", row["id"], line.id)
		ptav = {}
		for row in self.rows("product_template_attribute_value"):
			template = self.new("product.template", row["product_tmpl_id"])
			value = self.target("product.attribute.value", row["product_attribute_value_id"])
			found = template.attribute_line_ids.product_template_value_ids.filtered(
				lambda v: v.product_attribute_value_id.id == value) if template else None
			if found:
				ptav[row["id"]] = found[:1]
				self.remember("product.template.attribute.value", row["id"], found[:1].id)
				if row.get("price_extra"):
					found[:1].price_extra = float(row["price_extra"])
		combinations = self.pairs("product_variant_combination", "product_product_id", "product_template_attribute_value_id")
		Product = self.env["product.product"]
		variants = self.rows("product_product")
		for row in variants:
			if row["id"] in self.map["product.product"]:
				continue
			template = self.new("product.template", row["product_tmpl_id"])
			if not template:
				continue
			wanted = {ptav[v].id for v in combinations.get(row["id"], []) if v in ptav}
			candidates = template.with_context(active_test=False).product_variant_ids
			variant = candidates.filtered(lambda p: set(p.product_template_attribute_value_ids.ids) == wanted)[:1] \
				if wanted else candidates[:1]
			if not variant:
				self.note(f"The variant {row['id']} of «{template.name}» was not found here.")
				continue
			self.remember("product.product", row["id"], variant.id)
			values, translations, _later = self.convert("product.product", row)
			values.pop("company_id", None)
			barcode = values.get("barcode")
			if barcode and Product.search_count([("barcode", "=", barcode), ("id", "!=", variant.id)]):
				self.note(f"The barcode {barcode} of «{variant.display_name}» is already used here; it was left out.")
				values.pop("barcode")
			cost = values.pop("standard_price", None)
			try:
				with self.env.cr.savepoint():
					variant.write(values)
					if cost:
						variant.with_company(self.company).standard_price = cost
			except Exception as error:  # noqa: BLE001
				self.note(f"The variant «{variant.display_name}»: {str(error).splitlines()[0][:150]}")
		self.flush()
		self.images("product.template")
		self.images("product.product")
		self.copy("product.supplierinfo", self.rows("product_supplierinfo"), label="vendor prices")

	def pricelists(self):
		if "product.pricelist" not in self.env:
			return
		Pricelist = self.env["product.pricelist"]
		self.copy("product.pricelist", self.rows("product_pricelist"), match=lambda row: self.named(
			"product.pricelist", row, [("company_id", "in", [self.company.id, False])]), skip={"item_ids"})
		self.copy("product.pricelist.item", [row for row in self.rows("product_pricelist_item")
			if row["pricelist_id"] in self.map["product.pricelist"]])

	def hr(self):
		if "hr.employee" not in self.env:
			return
		self.copy("hr.department", self.rows("hr_department", order="parent_id NULLS FIRST, id"), skip={"manager_id"},
			match=lambda row: self.named("hr.department", row, [("company_id", "=", self.company.id)]))
		self.copy("hr.job", self.rows("hr_job"), match=lambda row: self.named(
			"hr.job", row, [("company_id", "in", [self.company.id, False])]))
		rows = self.rows("hr_employee", order="parent_id NULLS FIRST, id")
		if rows and "name" not in rows[0] and self.old.has("resource_resource"):
			names = {r["id"]: r["name"] for r in self.old.rows("SELECT id, name FROM resource_resource")}
			for row in rows:
				row["name"] = names.get(row["resource_id"])

		def extra(row, values):
			values["name"] = text(row.get("name")) or "-"
			user = self.target("res.users", row.get("user_id"))
			if user and not self.env["hr.employee"].search_count([("user_id", "=", user), ("company_id", "=", self.company.id)]):
				values["user_id"] = user
			return values

		def match(row):
			user = self.target("res.users", row.get("user_id"))
			Employee = self.env["hr.employee"]
			return (Employee.search([("user_id", "=", user), ("company_id", "=", self.company.id)], limit=1) if user else
				Employee) or Employee.search([("name", "=", text(row.get("name"))), ("company_id", "=", self.company.id)],
				limit=1)

		self.copy("hr.employee", rows, extra=extra, match=match, label="employees")
		for row in self.rows("hr_department"):
			department = self.new("hr.department", row["id"])
			manager = self.target("hr.employee", row.get("manager_id"))
			if department and manager and not department.manager_id:
				department.manager_id = manager
		self.images("hr.employee")

	def warehouses(self):
		if "stock.warehouse" not in self.env:
			return
		Warehouse = self.env["stock.warehouse"]
		main = Warehouse.search([("company_id", "=", self.company.id)], limit=1)
		for index, row in enumerate(self.rows("stock_warehouse")):
			if row["id"] in self.map["stock.warehouse"]:
				continue
			warehouse = Warehouse.search([("code", "=", row["code"]), ("company_id", "=", self.company.id)], limit=1) or \
				(main if index == 0 else None)
			if not warehouse:
				try:
					with self.env.cr.savepoint():
						warehouse = Warehouse.create({"name": row["name"], "code": row["code"][:5],
							"company_id": self.company.id})
				except Exception as error:  # noqa: BLE001
					self.note(f"The warehouse {row['name']} was not made: {str(error).splitlines()[0][:150]}")
					continue
			self.remember("stock.warehouse", row["id"], warehouse.id)
			for column, field in (("view_location_id", "view_location_id"), ("lot_stock_id", "lot_stock_id")):
				if row.get(column):
					self.remember("stock.location", row[column], warehouse[field].id)
			for column in ("in_type_id", "out_type_id", "int_type_id", "pick_type_id", "pack_type_id"):
				if row.get(column) and column in warehouse._fields and warehouse[column]:
					self.remember("stock.picking.type", row[column], warehouse[column].id)
		# The other locations of the old warehouses, under the locations they were under
		rows = self.rows("stock_location", "usage IN ('internal', 'transit', 'view')", order="parent_path, id") \
			if self.old.has("stock_location", "parent_path") else self.rows("stock_location", "usage IN ('internal', "
			"'transit', 'view')")
		rows = [row for row in rows if row["id"] not in self.map["stock.location"] and row.get("location_id") and
			self.target("stock.location", row["location_id"])]
		Location = self.env["stock.location"]

		def match(row):
			if row.get("barcode"):
				found = Location.search([("barcode", "=", row["barcode"]), ("company_id", "=", self.company.id)], limit=1)
				if found:
					return found
			return Location.search([("name", "=", row["name"]), ("location_id", "=", self.target("stock.location",
				row["location_id"]))], limit=1)

		self.copy("stock.location", rows, match=match, skip={"warehouse_id"}, label="stock locations")
		if "stock.lot" in self.env:
			self.copy("stock.lot", self.rows("stock_lot"), label="lots and serial numbers") if self.old.has("stock_lot") \
				else self.copy("stock.lot", self.rows("stock_production_lot"), table="stock_production_lot")

	def orders(self):
		"""Quotations and orders, with their old numbers and states; no delivery or receipt is made for them here"""
		for model, line_model, table, line_table in (("sale.order", "sale.order.line", "sale_order", "sale_order_line"),
				("purchase.order", "purchase.order.line", "purchase_order", "purchase_order_line")):
			if not self.old.has(table):
				continue
			if model not in self.env:
				count = self.old.value(f"SELECT count(*) FROM {table} WHERE company_id = %s", (self.cid,))
				if count:
					self.note(f"{count} records of {model} were not brought: that part of the program is not installed here.")
				continue
			rows = self.rows(table)
			states = {row["id"]: row["state"] for row in rows}
			orders = self.copy(model, rows, label=model.split(".")[0] + " orders")
			lines = [row for row in self.rows(line_table) if row["order_id"] in self.map[model]]
			self.copy(line_model, lines, label=model.split(".")[0] + " order lines")
			# What was delivered or received in the old system, which no transfer here says
			done = "qty_delivered" if model == "sale.order" else "qty_received"
			for row in lines:
				line = self.new(line_model, row["id"])
				if line and row.get(done) and done in line._fields and line[done] != float(row[done]):
					with self.env.cr.savepoint():
						line.write({done: float(row[done])})
			# The state last: a confirmed order made here from its lines would start deliveries and receipts
			if orders:
				by_state = defaultdict(list)
				reverse = {new: old for old, new in self.map[model].items()}
				for order in orders:
					by_state[states.get(reverse.get(order.id))].append(order.id)
				valid = [key for key, _label in self.env[model]._fields["state"]._description_selection(self.env)]
				for state, ids in by_state.items():
					state = {"done": "sale" if model == "sale.order" else "purchase"}.get(state, state) \
						if state not in valid else state
					if state in valid and state != "draft":
						self.env.cr.execute(f'UPDATE "{self.env[model]._table}" SET state = %s WHERE id = ANY(%s)', (state, ids))
				records = self.env[model].browse(orders.ids)
				records.invalidate_recordset(["state"])
				# What follows from the state (the lines' state, what is to invoice) worked out again
				records.modified(["state"])
				self.env.flush_all()

	def extras(self):
		"""Meetings, events, expenses, manufacturing, projects and leads: copied as they are, each kind when that
		part of the program is installed here"""
		def by_name(model):
			return lambda row: self.named(model, row, [("company_id", "in", [self.company.id, False])]
				if "company_id" in self.env[model]._fields else [])

		specs = [
			("calendar.event", "calendar_event", None, {"attendee_ids"}),
			("event.type", "event_type", by_name("event.type"), set()),
			("event.event", "event_event", None, {"registration_ids", "event_ticket_ids", "stage_id"}),
			("event.event.ticket", "event_event_ticket", None, set()),
			("event.registration", "event_registration", None, set()),
			("hr.expense", "hr_expense", None, {"sheet_id", "account_move_id"}),
			("mrp.workcenter", "mrp_workcenter", by_name("mrp.workcenter"), {"resource_id"}),
			("mrp.bom", "mrp_bom", None, {"bom_line_ids", "byproduct_ids", "operation_ids"}),
			("mrp.routing.workcenter", "mrp_routing_workcenter", None, set()),
			("mrp.bom.line", "mrp_bom_line", None, set()),
			("mrp.bom.byproduct", "mrp_bom_byproduct", None, set()),
			("project.task.type", "project_task_type", by_name("project.task.type"), set()),
			("project.project", "project_project", None, {"task_ids", "analytic_account_id"}),
			("project.task", "project_task", None, {"child_ids", "depend_on_ids", "dependent_ids",
				"personal_stage_type_ids", "personal_stage_type_id"}),
			("crm.team", "crm_team", by_name("crm.team"), set()),
			("crm.stage", "crm_stage", by_name("crm.stage"), set()),
			("crm.lead", "crm_lead", None, set()),
		]
		for model, table, match, skip in specs:
			if not self.old.has(table) or model not in self.env:
				if self.old.has(table) and self.old.value(f'SELECT count(*) FROM "{table}"'):
					self.note(f"The {model} records of the old system were not brought: that part of the program is "
						f"not installed here.")
				continue
			self.copy(model, self.rows(table, order="id"), match=match, skip=skip)
		# Manufacturing orders, without the components and products this version would plan anew from the bill
		# of materials: their moves come with the transfers
		if "mrp.production" in self.env and self.old.has("mrp_production"):
			rows = self.rows("mrp_production")
			states = {row["id"]: row["state"] for row in rows}

			def extra(row, values):
				values.update({"move_raw_ids": [], "move_finished_ids": [], "workorder_ids": []})
				return values

			made = self.copy("mrp.production", rows, extra=extra, skip={"state", "move_raw_ids", "move_finished_ids",
				"workorder_ids", "procurement_group_id"}, label="manufacturing orders")
			for old_id, state in states.items():
				production = self.target("mrp.production", old_id)
				if production and state:
					self.env.cr.execute("UPDATE mrp_production SET state = %s WHERE id = %s", (state, production))
			if made:
				self.env.invalidate_all()
			# Work orders and the time spent on them, with their states
			if "mrp.workorder" in self.env and self.old.has("mrp_workorder"):
				work = [row for row in self.rows("mrp_workorder") if row["production_id"] in self.map["mrp.production"]]
				self.copy("mrp.workorder", work, skip={"state", "time_ids", "move_raw_ids", "move_finished_ids",
					"move_line_ids"}, label="work orders")
				for row in work:
					order = self.target("mrp.workorder", row["id"])
					if order and row.get("state"):
						self.env.cr.execute("UPDATE mrp_workorder SET state = %s WHERE id = %s", (row["state"], order))
				if "mrp.workcenter.productivity" in self.env and self.old.has("mrp_workcenter_productivity"):
					self.copy("mrp.workcenter.productivity", [row for row in self.rows("mrp_workcenter_productivity")
						if row.get("workorder_id") in self.map["mrp.workorder"]], label="work times")
				self.env.invalidate_all()
		# Expenses in the states of this version
		if "hr.expense" in self.env and self.old.has("hr_expense", "state"):
			valid = [key for key, _l in self.env["hr.expense"]._fields["state"]._description_selection(self.env)]
			moved = {"reported": "submitted", "done": "paid", "posted": "paid"}
			for row in self.old.rows("SELECT id, state FROM hr_expense WHERE company_id = %s", (self.cid,)):
				expense = self.target("hr.expense", row["id"])
				state = row["state"] if row["state"] in valid else moved.get(row["state"])
				if expense and state in valid:
					self.env.cr.execute("UPDATE hr_expense SET state = %s WHERE id = %s", (state, expense))

	def insert(self, model, rows):
		"""Records written straight into their table, for history that must not act again here (the lines of a
		delivery done in the old system would move the stock a second time); [(old id, values)]"""
		if not rows:
			return
		Model = self.env[model]
		scalar = {name for name, field in Model._fields.items() if field.store and field.column_type and
			field.type not in ("many2many", "one2many")}
		columns = sorted({key for _old, values in rows for key in values if key in scalar})
		for old_id, values in rows:
			data = []
			for column in columns:
				value = values.get(column)
				if isinstance(value, (dict, list)):
					value = json.dumps(value)
				data.append(value)
			self.env.cr.execute(f'INSERT INTO "{Model._table}" ({", ".join(f'"{c}"' for c in columns)}, create_uid, '
				f'write_uid, create_date, write_date) VALUES ({", ".join(["%s"] * len(columns))}, 1, 1, now(), now()) '
				f'RETURNING id', data)
			self.remember(model, old_id, self.env.cr.fetchone()[0])

	def pickings(self):
		"""Receipts, deliveries and internal transfers with their lines, as they were. They do not move the stock
		here: the stock on hand comes from the quantities counted"""
		if "stock.picking" not in self.env or not self.old.has("stock_picking"):
			return
		Type = self.env["stock.picking.type"]
		for row in self.rows("stock_picking_type"):
			if row["id"] in self.map["stock.picking.type"]:
				continue
			warehouse = self.target("stock.warehouse", row.get("warehouse_id"))
			found = Type.search([("code", "=", row["code"]), ("warehouse_id", "=", warehouse or False),
				("company_id", "=", self.company.id)], limit=1) or Type.search([("code", "=", row["code"]),
				("company_id", "=", self.company.id)], limit=1)
			if found:
				self.remember("stock.picking.type", row["id"], found.id)
		rows = [row for row in self.rows("stock_picking") if self.target("stock.picking.type", row["picking_type_id"])]
		states = {row["id"]: row["state"] for row in rows}
		pickings = self.copy("stock.picking", rows, skip={"move_ids", "move_line_ids", "state", "backorder_id",
			"return_id"}, label="receipts and deliveries") or self.env["stock.picking"]
		productions = self.map.get("mrp.production", {})
		moves = [row for row in self.rows("stock_move") if row.get("picking_id") in self.map["stock.picking"] or
			row.get("raw_material_production_id") in productions or row.get("production_id") in productions]
		if not moves:
			return
		move_states = {row["id"]: row["state"] for row in moves}
		self.copy("stock.move", moves, skip={"state", "move_line_ids", "move_orig_ids", "move_dest_ids",
			"origin_returned_move_id", "returned_move_ids", "quantity", "picked"}, label="transfer lines")
		lines = []
		for row in self.rows("stock_move_line"):
			move = self.target("stock.move", row.get("move_id"))
			if not move or move_states.get(row["move_id"]) != "done" or row["id"] in self.map["stock.move.line"]:
				continue
			values, _t, _l = self.convert("stock.move.line", row, skip={"state"})
			values.update({"move_id": move, "state": "done"})
			if "quantity_product_uom" in row and row["quantity_product_uom"] is not None:
				values["quantity_product_uom"] = float(row["quantity_product_uom"])
			lines.append((row["id"], values))
		self.insert("stock.move.line", lines)
		# The states and dates of the old system; what was open waits here again, without any reservation
		Move, Picking = self.env["stock.move"], self.env["stock.picking"]
		for old_id, state in move_states.items():
			move = self.target("stock.move", old_id)
			if not move:
				continue
			state = state if state in ("done", "cancel", "draft") else "confirmed"
			old = next(row for row in moves if row["id"] == old_id)
			self.env.cr.execute("UPDATE stock_move SET state = %s, quantity = %s, picked = %s WHERE id = %s",
				(state, float(old.get("quantity") or old.get("quantity_done") or 0.0) if state == "done" else 0.0,
				state == "done", move))
		for old_id, state in states.items():
			picking = self.target("stock.picking", old_id)
			if picking:
				state = state if state in ("done", "cancel", "draft") else "confirmed"
				self.env.cr.execute("UPDATE stock_picking SET state = %s WHERE id = %s", (state, picking))
		changed = Move.browse(list(self.map["stock.move"].values()))
		self.env.invalidate_all()
		changed.modified(["state", "quantity"])
		Picking.browse(pickings.ids).modified(["state"])
		self.env.flush_all()
		# The value of each move in the old valuation, where this version keeps it on the move
		if "value" in Move._fields and self.old.has("stock_valuation_layer"):
			for row in self.old.rows("SELECT stock_move_id, sum(value) AS value FROM stock_valuation_layer WHERE "
					"stock_move_id IS NOT NULL AND company_id = %s GROUP BY stock_move_id", (self.cid,)):
				move = self.target("stock.move", row["stock_move_id"])
				if move:
					self.env.cr.execute("UPDATE stock_move SET value = %s WHERE id = %s", (float(row["value"] or 0), move))

	def moves(self):
		"""Every journal entry of the old company, with its lines as they were: as DRAFTS, with their old numbers"""
		Move = self.env["account.move"]
		rows = self.rows("account_move", order="date, id")
		self.move_states = {row["id"]: row["state"] for row in rows}
		todo = [row for row in rows if row["id"] not in self.map["account.move"]]
		total = len(todo)
		for start in range(0, total, BATCH):
			chunk = todo[start:start + BATCH]
			# The lines of these entries only: a company of some years has hundreds of thousands
			lines = defaultdict(list)
			for line in self.old.rows("SELECT * FROM account_move_line WHERE move_id = ANY(%s) ORDER BY move_id, sequence, "
					"id", ([row["id"] for row in chunk],)):
				lines[line["move_id"]].append(line)
			vals_list, olds = [], []
			for row in chunk:
				values, translations, later = self.convert("account.move", row, skip={"line_ids", "invoice_line_ids"})
				values["line_ids"] = [Command.create(self.line_values(line)) for line in lines[row["id"]]]
				values["state"] = "draft"
				vals_list.append(values)
				olds.append((row, translations, later))
			try:
				with self.env.cr.savepoint():
					made = Move.create(vals_list)
			except Exception:  # noqa: BLE001
				made = None
			if made is None:
				made = Move.browse()
				kept = []
				for values, item in zip(vals_list, olds):
					try:
						with self.env.cr.savepoint():
							made |= Move.create(values)
						kept.append(item)
					except Exception as error:  # noqa: BLE001
						self.failed["account.move"] += 1
						if self.failed["account.move"] <= 5:
							self.note(f"The entry {item[0].get('name')} of {item[0]['date']} was not brought: "
								f"{str(error).splitlines()[0][:200]}")
				olds = kept
			for (row, translations, later), move in zip(olds, made):
				self.remember("account.move", row["id"], move.id)
				if translations:
					self.translate(move, translations)
				self.counts["journal entries"] += 1
				self.match_lines(lines[row["id"]], move)
			self.flush()
			if total > 500 and (start // BATCH) % 10 == 0:
				self.say(f"    {min(start + BATCH, total)} of {total} entries")
		# Reversals and other references between entries, once all are here
		for row in rows:
			move = self.new("account.move", row["id"])
			reversed_id = self.target("account.move", row.get("reversed_entry_id"))
			if move and reversed_id and not move.reversed_entry_id:
				move.reversed_entry_id = reversed_id

	def match_lines(self, old_lines, move):
		"""Each old line of an entry to its line here: in the order they were made when the entry has as many, else
		by account and amount"""
		made = move.line_ids.sorted("id")
		if len(made) == len(old_lines):
			for line, record in zip(old_lines, made):
				self.remember("account.move.line", line["id"], record.id)
			return
		left = list(made)
		for line in old_lines:
			account = self.target("account.account", line["account_id"])
			balance = float(line.get("balance") or 0.0)
			record = next((r for r in left if r.account_id.id == account and abs(r.balance - balance) < 0.01), None)
			if record:
				left.remove(record)
				self.remember("account.move.line", line["id"], record.id)

	def line_values(self, line):
		values, _translations, _later = self.convert("account.move.line", line)
		values.pop("company_id", None)
		if "balance" not in values and ("debit" in line or "credit" in line):
			values["balance"] = float(line.get("debit") or 0) - float(line.get("credit") or 0)
		values.setdefault("amount_currency", values.get("balance", 0.0))
		return values

	def payments(self):
		if not self.old.has("account_payment"):
			return
		if self.old.has("account_payment", "date"):
			rows = self.rows("account_payment")
		else:
			# Odoo 17: a payment shares its journal entry's columns
			rows = self.old.rows("SELECT m.*, p.* FROM account_payment p JOIN account_move m ON m.id = p.move_id WHERE "
				"m.company_id = %s ORDER BY p.id", (self.cid,))

		def extra(row, values):
			move = self.new("account.move", row.get("move_id"))
			if move:
				values["move_id"] = move.id
				if not values.get("outstanding_account_id"):
					# The account of the bank side of its entry, which this version needs to make a payment
					destination = values.get("destination_account_id")
					liquidity = move.line_ids.filtered(lambda l: l.account_id.id != destination)[:1]
					if liquidity:
						values["outstanding_account_id"] = liquidity.account_id.id
			return values

		# Written as they were: made through the program, a payment works out its accounts anew, and a company
		# without the old settings could not make it at all
		todo = []
		for row in rows:
			if row["id"] in self.map["account.payment"]:
				continue
			values, _t, _l = self.convert("account.payment", row, skip={"state"})
			values = extra(row, values)
			values["state"] = "draft"
			invoices = values.pop("invoice_ids", None)
			todo.append((row["id"], values, invoices))
		self.insert("account.payment", [(old_id, values) for old_id, values, _i in todo])
		Payment = self.env["account.payment"]
		for old_id, _values, invoices in todo:
			payment = self.new("account.payment", old_id)
			if invoices and "invoice_ids" in Payment._fields:
				with self.env.cr.savepoint():
					payment.invoice_ids = invoices
			self.counts["payments"] += 1
		self.flush()
		for row in rows:
			payment = self.target("account.payment", row["id"])
			if payment:
				self.payment_states[payment] = row.get("state")
		for row in rows:
			payment = self.new("account.payment", row["id"])
			if payment and payment.move_id and "origin_payment_id" in payment.move_id._fields:
				payment.move_id.origin_payment_id = payment.id

	def statements(self):
		if not self.old.has("account_bank_statement_line"):
			return
		self.copy("account.bank.statement", self.rows("account_bank_statement"), skip={"line_ids"},
			label="bank statements")
		rows = self.rows("account_bank_statement_line") if self.old.has("account_bank_statement_line", "company_id") else \
			self.old.rows("SELECT l.* FROM account_bank_statement_line l JOIN account_move m ON m.id = l.move_id WHERE "
			"m.company_id = %s ORDER BY l.id", (self.cid,))
		Line = self.env["account.bank.statement.line"]
		for row in rows:
			if row["id"] in self.map["account.bank.statement.line"]:
				continue
			move = self.new("account.move", row["move_id"])
			if not move:
				continue
			values, _t, _l = self.convert("account.bank.statement.line", row, skip=set(self.env["account.move"]._fields))
			values["move_id"] = move.id
			try:
				with self.env.cr.savepoint():
					line = Line.create(values)
			except Exception as error:  # noqa: BLE001
				self.failed["account.bank.statement.line"] += 1
				if self.failed["account.bank.statement.line"] <= 3:
					self.note(f"A bank statement line of {row.get('payment_ref') or ''} was not brought: "
						f"{str(error).splitlines()[0][:200]}")
				continue
			self.remember("account.bank.statement.line", row["id"], line.id)
			self.counts["bank statement lines"] += 1

	def reconciliations(self):
		"""Which lines were reconciled with which in the old system: redone here once the entries are posted"""
		self.groups = []
		if not self.old.has("account_partial_reconcile"):
			return
		parent = {}

		def find(x):
			while parent.get(x, x) != x:
				parent[x] = parent.get(parent[x], parent[x])
				x = parent[x]
			return x

		for row in self.old.rows("SELECT debit_move_id, credit_move_id FROM account_partial_reconcile WHERE company_id = %s",
				(self.cid,)) if self.old.has("account_partial_reconcile", "company_id") else self.old.rows(
				"SELECT debit_move_id, credit_move_id FROM account_partial_reconcile"):
			a, b = row["debit_move_id"], row["credit_move_id"]
			parent.setdefault(a, a)
			parent.setdefault(b, b)
			parent[find(a)] = find(b)
		groups = defaultdict(list)
		for line in parent:
			groups[find(line)].append(line)
		for lines in groups.values():
			new = [self.target("account.move.line", line) for line in lines]
			if all(new) and len(new) > 1:
				self.groups.append(sorted(new))
			else:
				self.failed["reconciliations"] += 1
		self.counts["reconciliations to redo"] = len(self.groups)

	def stock(self):
		"""The quantities on hand in each location and lot: COUNTED here, not applied"""
		if "stock.quant" not in self.env or not self.old.has("stock_quant"):
			return
		rows = self.old.rows("SELECT q.product_id, q.location_id, q.lot_id, sum(q.quantity) AS quantity FROM stock_quant q "
			"JOIN stock_location l ON l.id = q.location_id WHERE l.usage = 'internal' AND q.company_id = %s GROUP BY "
			"q.product_id, q.location_id, q.lot_id HAVING sum(q.quantity) <> 0", (self.cid,))
		Quant = self.env["stock.quant"].with_context(inventory_mode=True)
		counted = 0
		for row in rows:
			product = self.new("product.product", row["product_id"])
			location = self.target("stock.location", row["location_id"])
			lot = self.target("stock.lot", row["lot_id"]) if row["lot_id"] else False
			if not product or not location or not product.is_storable:
				continue
			domain = [("product_id", "=", product.id), ("location_id", "=", location), ("lot_id", "=", lot or False)]
			quant = Quant.search(domain, limit=1)
			try:
				with self.env.cr.savepoint():
					if quant:
						quant.inventory_quantity = float(row["quantity"])
					else:
						Quant.create({"product_id": product.id, "location_id": location, "lot_id": lot or False,
							"inventory_quantity": float(row["quantity"])})
				counted += 1
			except Exception as error:  # noqa: BLE001
				self.note(f"The stock of «{product.display_name}» was not counted: {str(error).splitlines()[0][:150]}")
		self.counts["stock counted"] = counted

	def image(self, model, field, res_id):
		rows = self.old.rows("SELECT store_fname, db_datas FROM ir_attachment WHERE res_model = %s AND res_field = %s "
			"AND res_id = %s ORDER BY id DESC LIMIT 1", (model, field, res_id))
		if not rows:
			return None
		data = (self.backup.file(rows[0]["store_fname"]) if self.backup else None) if rows[0]["store_fname"] else \
			rows[0]["db_datas"]
		return base64.b64encode(bytes(data)).decode() if data else None

	def images(self, model):
		"""The pictures of the records of a model (contacts, products, employees)"""
		if not self.old.has("ir_attachment") or model not in self.env or "image_1920" not in self.env[model]._fields:
			return
		rows = self.old.rows("SELECT res_id, store_fname, db_datas FROM ir_attachment WHERE res_model = %s AND "
			"res_field = 'image_1920' ORDER BY id", (model,))
		for row in rows:
			record = self.new(model, row["res_id"])
			if not record or record.image_1920:
				continue
			data = (self.backup.file(row["store_fname"]) if self.backup else None) if row["store_fname"] else row["db_datas"]
			if data:
				try:
					with self.env.cr.savepoint():
						record.image_1920 = base64.b64encode(bytes(data))
					self.counts["pictures"] += 1
				except Exception:  # noqa: BLE001 - a picture Pillow cannot open stays out
					pass

	def attachments(self):
		"""The files attached to the records brought: PDFs of bills, documents of contacts..."""
		if not self.old.has("ir_attachment"):
			return
		models = [model for model, ids in self.map.items() if ids and model in self.env]
		rows = self.old.rows("SELECT * FROM ir_attachment WHERE res_model = ANY(%s) AND res_field IS NULL AND res_id IS NOT "
			"NULL AND type = 'binary' ORDER BY id", (models,))
		Attachment = self.env["ir.attachment"]
		for row in rows:
			if row["id"] in self.map["ir.attachment"]:
				continue
			res_id = self.target(row["res_model"], row["res_id"])
			if not res_id:
				continue
			data = (self.backup.file(row["store_fname"]) if self.backup else None) if row["store_fname"] else row["db_datas"]
			if data is None:
				self.failed["files missing from the backup"] += 1
				continue
			record = Attachment.create({"name": row["name"], "raw": bytes(data), "mimetype": row.get("mimetype"),
				"res_model": row["res_model"], "res_id": res_id, "description": row.get("description")})
			self.remember("ir.attachment", row["id"], record.id)
			self.counts["attached files"] += 1
		self.flush()

	def messages(self):
		"""The notes and messages written on the records brought, with their dates and authors"""
		if not self.old.has("mail_message"):
			return
		models = [model for model, ids in self.map.items() if ids and model in self.env and model != "ir.attachment" and
			"message_ids" in self.env[model]._fields]
		rows = self.old.rows("SELECT * FROM mail_message WHERE model = ANY(%s) AND message_type IN ('comment', 'email', "
			"'email_outgoing') ORDER BY id", (models,))
		attached = self.pairs("message_attachment_rel", "message_id", "attachment_id")
		Message = self.env["mail.message"].sudo()
		for row in rows:
			if row["id"] in self.map["mail.message"]:
				continue
			res_id = self.target(row["model"], row["res_id"])
			if not res_id or not (row.get("body") or attached.get(row["id"])):
				continue
			values = {"model": row["model"], "res_id": res_id, "body": row.get("body") or "", "subject": row.get("subject"),
				"date": row["date"], "message_type": row["message_type"], "email_from": row.get("email_from"),
				"author_id": self.target("res.partner", row.get("author_id")),
				"subtype_id": self.target("mail.message.subtype", row.get("subtype_id"))}
			files = [a for a in (self.target("ir.attachment", a) for a in attached.get(row["id"], [])) if a]
			if files:
				values["attachment_ids"] = [Command.set(files)]
			record = Message.create({key: value for key, value in values.items() if value is not None})
			self.remember("mail.message", row["id"], record.id)
			self.counts["notes and messages"] += 1
		self.flush()

	# --- what is left

	def left_out(self):
		"""The tables of the old database with data that was not brought, by the module they belong to"""
		if not self.old.has("ir_model"):
			return []
		brought = {self.env[model]._table for model in self.map if model in self.env}
		# Brought with others, or made again here from what was brought
		brought |= {"account_move_line", "account_partial_reconcile", "account_full_reconcile", "stock_quant",
			"account_payment_term_line", "account_analytic_line", "stock_valuation_layer", "account_tax_repartition_line",
			"product_template_attribute_line", "product_template_attribute_value", "stock_move_line", "hr_version",
			"resource_resource"}
		technical = ("ir_", "res_groups", "res_lang", "res_country", "res_currency", "bus_", "base_", "mail_",
			"web_", "auth_", "iap_", "digest", "res_config", "report_", "onboarding", "spreadsheet", "utm_",
			"product_template_attribute", "product_variant_combination", "decimal_precision", "barcode", "sms_",
			"snailmail", "uom_category", "resource_", "account_report", "account_tax_report", "account_payment_method",
			"account_reconcile_model", "account_journal_group", "account_root", "stock_route", "stock_rule",
			"stock_picking_type", "stock_location_route", "calendar_alarm", "fetchmail", "website_", "theme_",
			"html_editor", "account_account_res_company_rel", "res_users_settings", "res_company_users_rel", "rating_",
			"res_device", "res_users_log", "discuss_", "properties_", "veron_ai_", "stock_reference", "privacy_",
			"account_payment_register", "res_users_apikeys", "auth_totp", "portal_", "payment_method", "payment_provider",
			"sale_pdf_form_field", "event_mail", "calendar_attendee", "mrp_production_group", "product_value")
		transient = "AND m.transient IS NOT TRUE" if self.old.has("ir_model", "transient") else ""
		rows = self.old.rows(f"SELECT m.model, string_agg(DISTINCT d.module, ',') AS modules FROM ir_model m LEFT JOIN "
			f"ir_model_data d ON d.model = 'ir.model' AND d.res_id = m.id WHERE true {transient} GROUP BY m.model")
		views = {row["table_name"] for row in self.old.rows("SELECT table_name FROM information_schema.tables WHERE "
			"table_type = 'VIEW' AND table_schema = current_schema()")}
		left = []
		for row in rows:
			table = row["model"].replace(".", "_")
			if table in brought or table in views or table.startswith(technical) or not self.old.has(table):
				continue
			try:
				# Only what people made: the records a module brings with it have an external id
				count = self.old.value(f'SELECT count(*) FROM "{table}" t WHERE NOT EXISTS (SELECT 1 FROM ir_model_data d '
					f'WHERE d.model = %s AND d.res_id = t.id)', (row["model"],))
			except Exception:  # noqa: BLE001 - a view or a table of another kind
				self.old.cr.connection.rollback() if hasattr(self.old.cr, "connection") else None
				continue
			if count:
				left.append((row["model"], row["modules"] or "", count))
		return sorted(left, key=lambda item: -item[2])
