import json
import re

from odoo import models
from odoo.tools.translate import code_translations

TEXT_KEYS = ("text", "title", "label")
TAGS = re.compile(r"<[^>]+>")
# Words written inside formulas, as fallbacks or between numbers: only these, a formula's other
# quoted words are field names
FORMULA_WORDS = {'"No data"': '"بدون داده"', '" out of "': '" از "'}
TRANSLATE = re.compile(r'_t\("([^"]+)"\)')
LINK = re.compile(r"^\[([^\]]+)\]\((odoo://.+)\)$", re.S)


class SpreadsheetDashboard(models.Model):
	_inherit = "spreadsheet.dashboard"

	def _dashboard_is_empty(self):
		"""Odoo shows a sample in place of a dashboard without data: English, in dollars, of a furniture
		shop. The dashboard itself is shown, with its zeros until there is data."""
		return False

	def _get_serialized_readonly_dashboard(self):
		"""The texts of charts the web client does not translate (axis titles, carousel items...),
		translated as the dashboard's other words are: from its module, then any module"""
		body = super()._get_serialized_readonly_dashboard()
		lang = self.env.lang or "en_US"
		if lang.startswith("en"):
			return body
		data = json.loads(body)
		words = {}
		for module in self.env["ir.module.module"].sudo().search([("state", "=", "installed")]).mapped("name"):
			for message in code_translations.get_web_translations(module, lang)["messages"]:
				words.setdefault(message["id"], message["string"])
		module = data.get("translation_namespace")
		if module:
			for message in code_translations.get_web_translations(module, lang)["messages"]:
				words[message["id"]] = message["string"]
		# Some of Odoo's Persian keeps HTML around a title («<div>فاکتورها برتر</div>»)
		words = {source: TAGS.sub("", text).strip() for source, text in words.items()}
		for sheet in data["snapshot"].get("sheets", []):
			for figure in sheet.get("figures", []):
				_translate(figure.get("data"), words)
			# A title with a link to a view: «[Top Invoices](odoo://view/...)»
			for ref, cell in sheet.get("cells", {}).items():
				if isinstance(cell, str) and (match := LINK.match(cell)) and match.group(1) in words:
					sheet["cells"][ref] = f"[{words[match.group(1)]}]({match.group(2)})"
				elif isinstance(cell, str) and cell.startswith("="):
					for english, persian in FORMULA_WORDS.items():
						cell = cell.replace(english, persian)
					# _t("...") in a formula, with the cleaned Persian (Odoo's own may hold HTML)
					cell = TRANSLATE.sub(lambda m: _quoted(words[m.group(1)]) if m.group(1) in words else m.group(0), cell)
					sheet["cells"][ref] = cell
		return json.dumps(data)


def _quoted(text):
	return '"' + text.replace('"', '""') + '"'


def _translate(node, words):
	if isinstance(node, dict):
		for key, value in node.items():
			if key in TEXT_KEYS and isinstance(value, str) and value in words:
				node[key] = words[value]
			else:
				_translate(value, words)
	elif isinstance(node, list):
		for value in node:
			_translate(value, words)

