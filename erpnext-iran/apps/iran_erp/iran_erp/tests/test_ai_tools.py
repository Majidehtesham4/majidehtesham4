import datetime

from frappe.tests import UnitTestCase

from iran_erp.ai.tools import _field, _value


class TestAITools(UnitTestCase):
	def test_aggregate_strings_become_dicts(self):
		self.assertEqual(_field("sum(grand_total) as total"), {"SUM": "grand_total", "as": "total"})
		self.assertEqual(_field("COUNT(*) as invoices"), {"COUNT": "*", "as": "invoices"})
		self.assertEqual(_field("count(name)"), {"COUNT": "name", "as": "count"})
		self.assertEqual(_field("customer"), "customer")

	def test_dates_carry_jalali(self):
		self.assertEqual(_value(datetime.date(2025, 3, 21)), "2025-03-21 (۱۴۰۴/۰۱/۰۱)")
		self.assertEqual(_value({"d": [datetime.date(2026, 10, 11)]}), {"d": ["2026-10-11 (۱۴۰۵/۰۷/۱۹)"]})
