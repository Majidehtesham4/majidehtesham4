"""Restores a backup of an Odoo database (the zip of the database manager, or that zip unpacked: dump.sql,
manifest.json and the filestore folder) into a database of its own, next to the others.

Run inside the program's container by «odoo.ps1 restore <backup> <name>» or «./veron restore <backup> <name>».
It refuses a backup of another version of Odoo, lists the modules of the backup this installation does not have,
and by default neutralizes the copy: no e-mail is sent and no scheduled job or payment runs from it."""

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile


def manifest_of(path):
	if os.path.isdir(path):
		with open(os.path.join(path, "manifest.json"), encoding="utf-8") as handle:
			return json.load(handle)
	with zipfile.ZipFile(path) as archive:
		return json.loads(archive.read("manifest.json"))


def as_zip(path, folder):
	"""The unpacked backup put back in a zip, as Odoo restores it (stored, not compressed: it is read once)"""
	target = os.path.join(folder, "backup.zip")
	with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
		for root, _dirs, files in os.walk(path):
			for name in files:
				full = os.path.join(root, name)
				relative = os.path.relpath(full, path)
				if relative.split(os.sep)[0] in ("dump.sql", "manifest.json", "filestore"):
					archive.write(full, relative)
	return target


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("backup")
	parser.add_argument("database")
	parser.add_argument("--keep-live", action="store_true", help="do not neutralize: mails and jobs of the copy run")
	parser.add_argument("--check", action="store_true", help="only say whether it can be restored")
	args = parser.parse_args()

	import odoo
	from odoo.tools import config

	config.parse_config(["-c", "/etc/odoo/odoo.conf"])
	config["db_host"] = os.environ.get("HOST", "db")
	config["db_user"] = os.environ.get("USER", "odoo")
	config["db_password"] = os.environ.get("PASSWORD", "odoo")

	if not os.path.exists(args.backup):
		print("The backup is not found: %s" % args.backup)
		return 1
	try:
		manifest = manifest_of(args.backup)
	except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
		print("This is not a backup of the Odoo database manager (no manifest.json): %s" % error)
		return 1
	version = str(manifest.get("major_version") or manifest.get("version") or "?")
	ours = odoo.release.serie
	print("Backup of %s, Odoo %s, PostgreSQL %s, %s modules." % (manifest.get("db_name", "?"), version,
		manifest.get("pg_version", "?"), len(manifest.get("modules") or {})))
	if not version.replace("saas~", "").startswith(ours):
		print("")
		print("It cannot be restored here: it is Odoo %s and this program is Odoo %s." % (version, ours))
		print("A database opens only in its own version. The ways forward:")
		print(" 1. Upgrade it to %s first: OpenUpgrade (free, step by step, one version at a time) or" % ours)
		print("    upgrade.odoo.com (Odoo's service, for databases of Odoo Enterprise or Odoo Online).")
		print(" 2. Or bring over its data, not the database: export contacts, products, accounts and opening")
		print("    balances to Excel in the old Odoo and import them into a new database here.")
		return 2

	from odoo.modules.module import get_modules

	available = set(get_modules())
	missing = sorted(name for name in (manifest.get("modules") or {}) if name not in available)
	if missing:
		print("")
		print("%s modules of the backup are not installed here; their screens and data stay closed:" % len(missing))
		print("  " + ", ".join(missing[:60]) + (" ..." if len(missing) > 60 else ""))
		print("Modules of Odoo Enterprise or the company's own modules need their code in the addons folder.")
	if args.check:
		return 0

	import odoo.service.db as dbservice

	if dbservice.exp_db_exist(args.database):
		print("A database named %s already exists; choose another name." % args.database)
		return 1
	with tempfile.TemporaryDirectory() as folder:
		path = as_zip(args.backup, folder) if os.path.isdir(args.backup) else args.backup
		print("Restoring into %s (a few minutes for a large filestore)..." % args.database)
		# copy=True: a new identity, so the copy is never taken for the company's live database
		dbservice.restore_db(args.database, path, copy=True, neutralize_database=not args.keep_live)
	print("Done: database %s. Open http://localhost:8069/odoo?db=%s" % (args.database, args.database))
	if not args.keep_live:
		print("It is neutralized: outgoing mail servers, scheduled jobs and payment providers are turned off.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
