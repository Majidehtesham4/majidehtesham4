import logging
import os

from odoo import models
from odoo.tools.translate import TranslationImporter

_logger = logging.getLogger(__name__)

FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "i18n_modules")
# Corrections of the Persian Odoo itself ships (French or unrelated text in its fa.po): these replace it
FIXES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "i18n_fixes")


class IrModuleModule(models.Model):
	"""Persian for modules without it, mostly OCA's: i18n_modules/<module>.po, loaded each time the
	module's translations are (install, update, a language loaded). They fill what is missing only:
	a module's own Persian, or one corrected by hand, is kept."""

	_inherit = "ir.module.module"

	def _load_module_terms(self, modules, langs, overwrite=False):
		super()._load_module_terms(modules, langs, overwrite=overwrite)
		self._veron_load_persian(modules, langs)
		self._veron_load_fixes(modules, langs)
		self.env["veron.iran"]._brand_terms()

	def _veron_load_persian(self, modules, langs=("fa_IR",)):
		langs = [lang for lang in langs if lang.startswith("fa")]
		files = [(m, os.path.join(FOLDER, f"{m}.po")) for m in modules]
		files = [(m, path) for m, path in files if os.path.isfile(path)]
		if not langs or not files:
			return
		importer = TranslationImporter(self.env.cr, verbose=False)
		for lang in langs:
			for module, path in files:
				importer.load_file(path, lang, module=module)
		importer.save(overwrite=False)
		_logger.info("ERP-VERON: Persian of %s", ", ".join(m for m, _p in files))

	def _veron_load_fixes(self, modules, langs=("fa_IR",)):
		langs = [lang for lang in langs if lang.startswith("fa")]
		files = [(m, os.path.join(FIXES, f"{m}.po")) for m in modules]
		files = [(m, path) for m, path in files if os.path.isfile(path)]
		if not langs or not files:
			return
		importer = TranslationImporter(self.env.cr, verbose=False)
		for lang in langs:
			for module, path in files:
				importer.load_file(path, lang, module=module)
		importer.save(overwrite=True)
		_logger.info("ERP-VERON: Persian corrected in %s", ", ".join(m for m, _p in files))
