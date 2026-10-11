import datetime

from frappe.tests import UnitTestCase

from iran_erp.utils.jalali import format_jalali, jalali_year_bounds, to_gregorian
from iran_erp.utils.national_id import (
	is_valid_economic_code,
	is_valid_legal_national_id,
	is_valid_national_code,
)


class TestJalali(UnitTestCase):
	def test_nowruz(self):
		self.assertEqual(format_jalali("2025-03-21", persian_digits=False), "1404/01/01")
		self.assertEqual(format_jalali("2026-03-21", "long"), "۱ فروردین ۱۴۰۵")

	def test_leap_year(self):
		# 1403 is a leap year, so Esfand has 30 days
		self.assertEqual(format_jalali("2025-03-20", persian_digits=False), "1403/12/30")
		self.assertEqual(jalali_year_bounds(1403), (datetime.date(2024, 3, 20), datetime.date(2025, 3, 20)))
		self.assertEqual(jalali_year_bounds(1404), (datetime.date(2025, 3, 21), datetime.date(2026, 3, 20)))

	def test_round_trip(self):
		self.assertEqual(to_gregorian(1405, 7, 19), datetime.date(2026, 10, 11))


class TestIranianIds(UnitTestCase):
	def test_national_code(self):
		self.assertTrue(is_valid_national_code("0499370899"))
		self.assertTrue(is_valid_national_code("۰۴۹۹۳۷۰۸۹۹"))
		self.assertFalse(is_valid_national_code("0499370898"))
		self.assertFalse(is_valid_national_code("1111111111"))
		self.assertFalse(is_valid_national_code("12345"))

	def test_legal_national_id(self):
		self.assertTrue(is_valid_legal_national_id("10320894878"))
		self.assertFalse(is_valid_legal_national_id("10320894877"))

	def test_economic_code(self):
		self.assertTrue(is_valid_economic_code("0499370899"))
		self.assertTrue(is_valid_economic_code("10320894878"))
		self.assertTrue(is_valid_economic_code("411111111111"))
		self.assertFalse(is_valid_economic_code("123"))
