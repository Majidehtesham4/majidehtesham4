from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged


def answer(body):
	response = MagicMock()
	response.json.return_value = body
	response.raise_for_status.return_value = None
	return response


@tagged("post_install", "-at_install")
class TestRates(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = cls.env.company
		cls.usd = cls.env.ref("base.USD")
		cls.eur = cls.env.ref("base.EUR")

	def source(self, **values):
		values.setdefault("api_key", "K")
		return self.env["veron.currency.source"].create(dict({"name": "نوسان", "line_ids": [
			(0, 0, {"currency_id": self.usd.id}), (0, 0, {"currency_id": self.eur.id})]}, **values))

	def rate(self, currency):
		return self.env["res.currency.rate"].search([("currency_id", "=", currency.id), ("company_id", "=", self.company.id)],
			order="name desc", limit=1)

	def test_navasan_in_toman(self):
		if self.company.currency_id.name != "IRR":
			self.skipTest("the company's currency is not the rial")
		source = self.source()
		with patch("requests.get", return_value=answer({"usd": {"value": "105,200"}, "eur": {"value": "۱۲۰۵۰۰"}})) as get:
			source.action_fetch()
		self.assertEqual(get.call_args.kwargs["params"], {"api_key": "K"})
		self.assertEqual(self.rate(self.usd).inverse_company_rate, 1_052_000, "toman to rial")
		self.assertEqual(self.rate(self.eur).inverse_company_rate, 1_205_000)
		self.assertFalse(source.last_error)

	def test_json_path_missing_and_jump(self):
		if self.company.currency_id.name != "IRR":
			self.skipTest("the company's currency is not the rial")
		source = self.source(kind="json", url="https://rates.example/api", unit="rial",
			line_ids=[(0, 0, {"currency_id": self.usd.id, "key": "rates.USD.sell"})])
		with patch("requests.get", return_value=answer({"rates": {"USD": {"sell": 1_000_000}}})):
			source.action_fetch()
		self.assertEqual(self.rate(self.usd).inverse_company_rate, 1_000_000)
		yesterday = self.rate(self.usd)
		yesterday.name = "2026-01-01"
		with patch("requests.get", return_value=answer({"rates": {"USD": {"sell": 3_000_000}}})):
			source.action_fetch()
		self.assertIn("USD", source.last_error, "a jump of 200% is not used")
		self.assertEqual(self.rate(self.usd), yesterday)
		with patch("requests.get", return_value=answer({"rates": {}})):
			source.with_context(lang="en_US").action_fetch()
		self.assertIn("no rate", source.last_error)
