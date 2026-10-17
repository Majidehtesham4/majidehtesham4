"""Complete Persian guides for the pages of the system, shown by the «آموزش» button.

Each module here holds GUIDES (forms and lists, by DocType name), REPORTS (by report name) or
WORKSPACES (by workspace name). A guide is a dict of any of:

	about     what the page is for and when to use it (a few sentences)
	before    what has to exist first (list)
	steps     the usual work on the page, step by step (list)
	fields    field name (or report filter name) -> what it means and what to enter
	columns   report column name -> what it shows
	after     what saving or «ثبت نهایی» changes in the accounts and the stock
	mistakes  common mistakes and how to put them right (list)
	tips      (list)
	example   a short worked example with Iranian names, rials and Jalali dates
	related   names of related DocTypes, shown as links to their guides

The short guides in iran_erp.help.guides fill what a guide here leaves out.
"""

from importlib import import_module

MODULES = ("accounting", "selling_buying", "stock_more", "reports", "dealership")


def _collect(name: str) -> dict:
	merged = {}
	for module in MODULES:
		try:
			content = import_module(f"iran_erp.help.content.{module}")
		except ImportError:
			continue
		merged.update(getattr(content, name, {}) or {})
	return merged


GUIDES = _collect("GUIDES")
REPORTS = _collect("REPORTS")
WORKSPACES = _collect("WORKSPACES")
