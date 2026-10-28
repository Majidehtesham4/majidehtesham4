"""Every translation file of the program's modules is read the way Odoo reads it when a module is installed: one
entry without its module stops the install"""

import glob
import os

from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import PoFileReader


@tagged("post_install", "-at_install")
class TestTranslationFiles(TransactionCase):
	def test_every_po_file_reads(self):
		addons = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
		files = sorted(glob.glob(os.path.join(addons, "*", "i18n", "*.po")))
		self.assertTrue(files)
		for path in files:
			with self.subTest(path=os.path.relpath(path, addons)):
				self.assertTrue(sum(1 for _entry in PoFileReader(path)) >= 0)
