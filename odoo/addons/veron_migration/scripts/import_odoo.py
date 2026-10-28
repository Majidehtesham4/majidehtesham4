"""Brings a company from a backup of Odoo 17 or 18 (Community or Enterprise) into a database of this program, with
its history: run inside the program's container by «odoo.ps1 import18 <backup> <database>» or «./veron import18
<backup> <address>».

The backup (the zip of the database manager, or its unpacked folder) is loaded into a database of its own
(<database>_odoo18) and only read. The parts of the program the old company used (purchase, inventory,
manufacturing...) are installed in <database>, then everything is brought: see veron_migration/services/importer.py.
Nothing is posted or applied: a person confirms it in the program, on Settings, Brought From Odoo."""

import argparse
import os
import sys
import zipfile

# The parts of Odoo Community installed here when the old company used them
COMMUNITY = ["sale_management", "sale_stock", "purchase", "purchase_stock", "stock", "stock_account", "mrp",
	"mrp_account", "hr", "hr_expense", "project", "hr_timesheet", "crm", "event", "event_sale", "sale_purchase",
	"purchase_mrp", "sale_mrp", "stock_landed_costs", "mrp_landed_costs", "account_payment", "point_of_sale",
	"calendar", "fleet", "maintenance", "repair", "hr_holidays", "hr_recruitment", "lunch", "sale_expense",
	"sale_purchase_stock", "stock_dropshipping"]


def say(text=""):
	print(text, flush=True)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("backup")
	parser.add_argument("database")
	parser.add_argument("--company", type=int, help="the number of the company in the backup, when it has several")
	parser.add_argument("--reload", action="store_true", help="load the backup anew into its own database")
	parser.add_argument("--check", action="store_true", help="only say what the backup has")
	parser.add_argument("--from-db", help="read an old database already on this server instead of a backup (give - as "
		"the backup)")
	args = parser.parse_args()

	import odoo  # noqa: F401
	from odoo.modules import module as modules
	from odoo.tools import config

	config.parse_config(["-c", "/etc/odoo/odoo.conf"])
	config["db_host"] = os.environ.get("HOST", "db")
	config["db_user"] = os.environ.get("USER", "odoo")
	config["db_password"] = os.environ.get("PASSWORD", "odoo")
	modules.initialize_sys_path()
	# Only warnings and errors from the program itself: what this tool says is enough to follow it
	import logging

	logging.getLogger("odoo").setLevel(logging.WARNING)

	from odoo.addons.veron_migration.services import source

	if args.from_db:
		backup = source.Backup(None, filestore=config.filestore(args.from_db))
		host, user, password = config["db_host"], config["db_user"], config["db_password"]
		probe = source.Old.connect(f"host={host} user={user} password={password} dbname={args.from_db}")
		base = probe.value("SELECT latest_version FROM ir_module_module WHERE name = 'base'") or "?"
		installed = [row["name"] for row in probe.rows("SELECT name FROM ir_module_module WHERE state = 'installed'")]
		manifest = {"db_name": args.from_db, "major_version": ".".join(base.split(".")[:2]),
			"modules": dict.fromkeys(installed, "")}
	elif not os.path.exists(args.backup):
		say("The backup is not found: %s" % args.backup)
		return 1
	else:
		backup = source.Backup(args.backup)
		try:
			manifest = backup.manifest()
		except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
			say("This is not a backup of the Odoo database manager (no manifest.json): %s" % error)
			return 1
	version = str(manifest.get("major_version") or manifest.get("version") or "?")
	edition = "Enterprise" if "e" in (manifest.get("version_info") or [])[-1:] else "Community"
	say(f"Backup of {manifest.get('db_name', '?')}: Odoo {version} {edition}, {len(manifest.get('modules') or {})} modules.")
	if not version.split(".")[0] in ("16", "17", "18") and not args.from_db:
		say("This tool brings companies from Odoo 16, 17 or 18. For %s, use «restore» when it is this program's version."
			% version)
		return 2

	import odoo.service.db as dbservice
	from odoo import SUPERUSER_ID, api
	from odoo.modules.registry import Registry

	if not dbservice.exp_db_exist(args.database):
		say(f"There is no database {args.database}. Make it first, with the programs of ERP-VERON:")
		say(f"  .\\odoo.ps1 createdb {args.database}")
		say(f"  .\\odoo.ps1 install veron_apps {args.database}")
		return 1
	old_db = args.from_db or f"{args.database}_odoo18"
	dsn = f"host={config['db_host']} user={config['db_user']} password={config['db_password']} dbname={old_db}" \
		if args.from_db else source.load(backup, old_db, reload=args.reload, say=say)
	old = source.Old.connect(dsn)
	if args.check:
		for table, label in (("res_partner", "contacts"), ("product_product", "products"), ("account_move", "journal entries"),
				("account_payment", "payments"), ("sale_order", "sale orders"), ("purchase_order", "purchase orders"),
				("stock_quant", "stock rows"), ("hr_employee", "employees"), ("ir_attachment", "files")):
			if old.has(table):
				say(f"  {label}: {old.value(f'SELECT count(*) FROM {table}'):,}")
		return 0

	# The parts of the program the old company used, and this tool's own module
	wanted = ["veron_migration"] + [name for name in COMMUNITY if name in (manifest.get("modules") or {})]
	registry = Registry(args.database)
	with registry.cursor() as cr:
		env = api.Environment(cr, SUPERUSER_ID, {})
		env["ir.module.module"].update_list()
		missing = env["ir.module.module"].search([("name", "in", wanted), ("state", "!=", "installed")])
		names = missing.mapped("name")
	if names:
		say("Installing what the old company used: %s (a few minutes)..." % ", ".join(names))
		with registry.cursor() as cr:
			env = api.Environment(cr, SUPERUSER_ID, {})
			env["ir.module.module"].search([("name", "in", names)]).button_immediate_install()
		registry = Registry(args.database)

	from odoo.addons.veron_migration.services.importer import Importer

	with registry.cursor() as cr:
		env = api.Environment(cr, SUPERUSER_ID, {"lang": "fa_IR"})
		if "account.move" not in env:
			say(f"Accounting is not installed in {args.database}: .\\odoo.ps1 install veron_apps {args.database}")
			return 1
		say(f"Bringing it into {args.database}:")
		work = Importer(env, old, backup, version, args.company, say=say)
		import traceback

		stopped = []
		for step in work.steps():
			name = step.__name__.replace("_", " ")
			say(f"  {name}...")
			try:
				step()
				work.flush()
				env.flush_all()
				cr.commit()
			except Exception as error:  # noqa: BLE001 - one part that fails does not stop the others
				cr.rollback()
				env.invalidate_all()
				# What this part made is undone: the records remembered by it are looked up again
				work.pending = []
				work.map.clear()
				work._load_map()
				stopped.append(name)
				say(f"    STOPPED: {str(error).splitlines()[0][:300]}")
				say("    " + traceback.format_exc().strip().splitlines()[-3][:300])
				work.note(f"The part «{name}» stopped: {str(error).splitlines()[0][:300]}")
		migration = env["veron.migration"]._record(work, version, old_db)
		try:
			migration.action_compare()
		except Exception as error:  # noqa: BLE001 - the comparison is made again from the page
			cr.rollback()
			say(f"The comparison could not be made: {error}")
		cr.commit()
		if stopped:
			say("")
			say("These parts stopped with an error and were not brought: " + ", ".join(stopped))
			say("Send this whole output; running the command again brings only what is missing.")
		say("")
		say("Brought:")
		for name, count in work.counts.items():
			if count:
				say(f"  {name}: {count:,}")
		failed = {name: count for name, count in work.failed.items() if count}
		if failed:
			say("Not brought because of an error (see «To check»):")
			for name, count in failed.items():
				say(f"  {name}: {count:,}")
		if work.notes:
			say("")
			say("To check:")
			for note in work.notes[:60]:
				say("  - " + note)
			if len(work.notes) > 60:
				say(f"  ... and {len(work.notes) - 60} more, on the migration's page")
		left = work.left_out()
		if left:
			say("")
			say("Data of the old system that has no place here (module, records):")
			for model, modules, count in left[:40]:
				say(f"  {model} ({modules}): {count:,}")
	say("")
	say("Done. Nothing was posted or applied. Open the program, Settings, Brought From Odoo:")
	say("  1. Comparison: the balance of each account here next to the old system.")
	say("  2. Confirm and Post the Entries: they are posted with their old numbers, then the reconciliations are redone.")
	say("  3. Apply the Stock Counted, after checking it in Inventory, Physical Inventory.")
	say("  4. Users Brought: they are archived and without passwords; activate each and send the invitation.")
	say(f"The old database stays as {old_db}; delete it in the database manager once all is confirmed.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
