"""Persian of the texts written in code (Python messages, the web client's texts), which Odoo reads from
each module's own i18n folder only:
- i18n_modules/<module>.po adds what a module, mostly an OCA one, has no Persian for;
- i18n_overrides.json replaces a few of Odoo's own words, e.g. «ربع» for Quarter, which is a season in Shamsi.
Read once per module and language, as Odoo does."""

import json
import os

from odoo.tools import translate
from odoo.tools.misc import file_open

ROOT = os.path.dirname(os.path.dirname(__file__))

with open(os.path.join(ROOT, "i18n_overrides.json"), encoding="utf-8") as f:
	OVERRIDES = json.load(f)

_get_code_translations = translate.CodeTranslations._get_code_translations


def _veron_code_translations(module_name, lang, filter_func):
	translations = _get_code_translations(module_name, lang, filter_func)
	if not lang.startswith("fa"):
		return translations
	path = os.path.join(ROOT, "i18n_modules", f"{module_name}.po")
	if os.path.isfile(path):
		with file_open(path, mode="rb") as fileobj:
			extra = translate.CodeTranslations._read_code_translations_file(fileobj, filter_func)
		translations = {**extra, **translations}
	for src, value in OVERRIDES.items():
		if src in translations:
			translations[src] = value
	return translations


translate.CodeTranslations._get_code_translations = staticmethod(_veron_code_translations)
