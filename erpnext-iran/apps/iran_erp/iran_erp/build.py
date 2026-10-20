"""Which build of the app is running: the commit and time update.ps1 wrote before building, shown on
the home page and in the assistant, so an update can be seen to have happened."""

import json
import os

import frappe

BUILD_FILE = os.path.join(os.path.dirname(__file__), "build_info.json")


def build_label() -> str:
	from iran_erp import __version__

	try:
		with open(BUILD_FILE, encoding="utf-8-sig") as f:
			info = json.load(f)
	except (OSError, ValueError):
		return __version__
	commit = (info.get("commit") or "").strip()
	built = (info.get("built") or "").strip()
	if built:
		from iran_erp.utils.jalali import format_jalali

		try:
			date, _sep, time = built.partition(" ")
			built = f"{format_jalali(date, persian_digits=False)} {time}".strip()
		except Exception:
			frappe.clear_last_message()
	return " · ".join(p for p in (commit, built) if p) or __version__
