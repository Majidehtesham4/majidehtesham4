"""The owner's panel: every business environment (site) on this server, seen from the main site.

It shows each business with its address, its users and whether it has the last update, and runs
that update for one business or for all of them (deploy/update.ps1 does the whole update: new code,
then this step for every business). To work inside a business's system, open its address and log
in, or run «business.ps1 open <name>» on the server for a one-time Administrator login.
"""

import hashlib
import os
import subprocess

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

UPDATE_STATUS = "iran_owner_update"
_code_version = {}


def is_owner_site() -> bool:
	main = frappe.conf.get("iran_owner_site") or frappe.conf.get("default_site") or "frontend"
	return frappe.local.site == main


def _check():
	frappe.only_for("System Manager")
	if not is_owner_site():
		frappe.throw(_("The panel of customer systems is only on the main site."), frappe.PermissionError)


def code_version() -> str:
	"""A fingerprint of what a business's database has to match: the document types and patches of
	this app and the versions of the software underneath. It changes when an update needs migrating."""
	if "value" not in _code_version:
		import erpnext

		digest = hashlib.sha1(f"{frappe.__version__}|{erpnext.__version__}".encode())
		app = frappe.get_app_path("iran_erp")
		for root, dirs, files in os.walk(app):
			dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "tests", "public", "locale"))
			for name in sorted(files):
				if name.endswith(".json") or name == "patches.txt":
					with open(os.path.join(root, name), "rb") as f:
						digest.update(f.read())
		_code_version["value"] = digest.hexdigest()[:12]
	return _code_version["value"]


def record_code_version():
	"""after_migrate: this site's database now matches the code."""
	frappe.db.set_default("iran_code_version", code_version())


def other_sites() -> list[str]:
	from frappe.utils import get_sites

	return sorted(site for site in get_sites(frappe.local.sites_path) if site != frappe.local.site)


def _site_config(site: str) -> frappe._dict:
	return frappe._dict(
		frappe.get_site_config(frappe.local.sites_path, os.path.join(frappe.local.sites_path, site))
	)


def site_url(site: str) -> str:
	"""A business's address: its site name, with the scheme and port the panel is opened with."""
	conf = _site_config(site)
	if conf.get("host_name"):
		return conf.host_name.rstrip("/")
	host = frappe.get_request_header("Host") or ""
	port = f":{host.rsplit(':', 1)[1]}" if ":" in host else ""
	scheme = frappe.get_request_header("X-Forwarded-Proto") or "http"
	return f"{scheme}://{site}{port}"


def _facts(site: str) -> dict:
	"""What the panel shows about a business, read from its database (read only)."""
	import MySQLdb

	conf = _site_config(site)
	facts = {"site": site, "url": site_url(site)}
	try:
		connection = MySQLdb.connect(
			host=conf.db_host or "localhost",
			port=cint(conf.db_port) or 3306,
			user=conf.db_user or conf.db_name,
			passwd=conf.db_password,
			db=conf.db_name,
			charset="utf8mb4",
			connect_timeout=5,
		)
	except Exception as e:
		facts["error"] = str(e)[:200]
		return facts
	try:
		cursor = connection.cursor()

		def value(query, args=()):
			try:
				cursor.execute(query, args)
				row = cursor.fetchone()
				return row[0] if row else None
			except Exception:
				return None

		def single(doctype, field):
			return value("select value from tabSingles where doctype=%s and field=%s", (doctype, field))

		facts.update(
			title=single("Iran ERP Settings", "trade_name")
			or value("select name from tabCompany order by creation limit 1"),
			business_type=single("Iran Setup", "business_type"),
			users=cint(
				value(
					"select count(*) from tabUser where enabled=1 and user_type='System User'"
					" and name not in ('Administrator', 'Guest')"
				)
			),
			last_active=value(
				"select max(last_active) from tabUser where name not in ('Administrator', 'Guest')"
			),
			setup_complete=cint(
				value("select is_setup_complete from `tabInstalled Application` where app_name='frappe'")
			),
			code_version=value(
				"select defvalue from tabDefaultValue where parent='__default' and defkey='iran_code_version'"
			),
		)
	finally:
		connection.close()
	facts["up_to_date"] = facts.get("code_version") == code_version()
	if facts.get("last_active"):
		facts["last_active"] = str(facts["last_active"])
	return facts


@frappe.whitelist()
def get_panel() -> dict:
	_check()
	return {
		"main": {
			"site": frappe.local.site,
			"up_to_date": frappe.db.get_default("iran_code_version") == code_version(),
		},
		"sites": [_facts(site) for site in other_sites()],
		"code_version": code_version(),
		"update": frappe.cache.get_value(UPDATE_STATUS, shared=True),
	}


@frappe.whitelist(methods=["POST"])
def start_update(site: str | None = None) -> dict:
	"""Bring one business (or every business and this main site) up to the code: bench migrate."""
	_check()
	status = frappe.cache.get_value(UPDATE_STATUS, shared=True)
	if status and status.get("running"):
		frappe.throw(_("An update is already running."))
	if site:
		if site not in other_sites():
			frappe.throw(_("No such business on this server."))
		sites = [site]
	else:
		sites = [*other_sites(), frappe.local.site]
	_set_status({"running": True, "sites": sites, "done": [], "failed": {}, "current": None})
	frappe.enqueue("iran_erp.owner.run_update", queue="long", timeout=4 * 3600, sites=sites)
	return frappe.cache.get_value(UPDATE_STATUS, shared=True)


def _set_status(status):
	frappe.cache.set_value(UPDATE_STATUS, status, expires_in_sec=7 * 24 * 3600, shared=True)


def run_update(sites: list[str]):
	"""Background job: migrate each site in turn with the bench command, as an update does."""
	bench = os.path.abspath(os.path.join(frappe.local.sites_path, ".."))
	status = {"running": True, "sites": sites, "done": [], "failed": {}, "current": None}
	for site in sites:
		status["current"] = site
		_set_status(status)
		try:
			result = subprocess.run(
				["bench", "--site", site, "migrate"],
				cwd=bench,
				capture_output=True,
				text=True,
				timeout=3600,
			)
			if result.returncode:
				status["failed"][site] = (result.stderr or result.stdout)[-1500:]
			else:
				status["done"].append(site)
		except Exception as e:
			status["failed"][site] = str(e)[-1500:]
	status.update(running=False, current=None, finished=str(now_datetime()))
	_set_status(status)


@frappe.whitelist()
def update_status() -> dict | None:
	_check()
	return frappe.cache.get_value(UPDATE_STATUS, shared=True)
