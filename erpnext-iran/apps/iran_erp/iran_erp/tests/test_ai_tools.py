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


class TestStatementParsing(UnitTestCase):
	def test_amounts(self):
		from iran_erp.ai.files import parse_amount

		self.assertEqual(parse_amount("1,250,000"), 1250000)
		self.assertEqual(parse_amount("۱٬۲۵۰٬۰۰۰"), 1250000)
		self.assertEqual(parse_amount("(500)"), -500)
		self.assertEqual(parse_amount("500-"), -500)
		self.assertEqual(parse_amount(12.5), 12.5)
		self.assertIsNone(parse_amount(""))
		self.assertIsNone(parse_amount("-"))

	def test_dates(self):
		from iran_erp.ai.files import parse_date

		self.assertEqual(parse_date("1405/07/20"), datetime.date(2026, 10, 12))
		self.assertEqual(parse_date("۱۴۰۵/۰۷/۲۰ ۱۰:۳۰"), datetime.date(2026, 10, 12))
		self.assertEqual(parse_date("14050720"), datetime.date(2026, 10, 12))
		self.assertEqual(parse_date("2026-10-12"), datetime.date(2026, 10, 12))
		self.assertEqual(parse_date(datetime.datetime(2026, 10, 12, 9, 0)), datetime.date(2026, 10, 12))
		self.assertIsNone(parse_date("1405/12/30"))
		self.assertIsNone(parse_date("شرح"))

	def test_statement_lines(self):
		from iran_erp.ai.bank import statement_lines

		headers = ["تاریخ", "شرح", "برداشت", "واریز", "مانده"]
		rows = [
			["1405/07/18", "واریز مشتری", "", "50,000,000", "50,000,000"],
			["1405/07/19", "کارمزد", "12,000", "", "49,988,000"],
			["", "جمع", "12,000", "50,000,000", ""],
		]
		lines = statement_lines(
			rows,
			headers,
			{
				"date": "تاریخ",
				"description": "شرح",
				"withdrawal": "برداشت",
				"deposit": "واریز",
				"balance": "مانده",
			},
		)
		self.assertEqual([line["amount"] for line in lines], [50_000_000, -12_000])
		self.assertEqual(lines[1]["balance"], 49_988_000)

	def test_match_prefers_reference_then_closest_date(self):
		import frappe

		from iran_erp.ai.bank import match

		def entry(no, date, amount, reference=""):
			return frappe._dict(
				voucher_type="Journal Entry",
				voucher_no=no,
				posting_date=date,
				amount=amount,
				reference=reference,
			)

		lines = [
			{"row": 1, "date": datetime.date(2026, 10, 10), "amount": 1000, "reference": "777"},
			{"row": 2, "date": datetime.date(2026, 10, 10), "amount": 1000, "reference": ""},
			{"row": 3, "date": datetime.date(2026, 10, 10), "amount": -30, "reference": ""},
		]
		entries = [
			entry("JV-1", datetime.date(2026, 10, 10), 1000),
			entry("JV-2", datetime.date(2026, 10, 12), 1000, "777"),
			entry("JV-3", datetime.date(2026, 10, 20), 1000),
		]
		matched, unmatched, unused = match(lines, entries, 3)
		pairs = {line["row"]: e.voucher_no for line, e in matched}
		self.assertEqual(pairs, {1: "JV-2", 2: "JV-1"})
		self.assertEqual([line["row"] for line in unmatched], [3])
		self.assertEqual([e.voucher_no for e in unused], ["JV-3"])


class TestStoredHistory(UnitTestCase):
	def test_file_parts_are_not_stored(self):
		from iran_erp.ai.assistant import _trim

		message = {
			"role": "user",
			"content": [
				{"type": "text", "text": "این فاکتور را ثبت کن"},
				{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
			],
		}
		stored = _trim(message)
		self.assertEqual(stored["content"][0]["text"], "این فاکتور را ثبت کن")
		self.assertNotIn("base64", str(stored))


class TestAnthropicFormat(UnitTestCase):
	def test_request_conversion(self):
		from iran_erp.ai.anthropic import to_anthropic_request

		messages = [
			{"role": "system", "content": "be brief"},
			{
				"role": "user",
				"content": [
					{"type": "text", "text": "این فاکتور"},
					{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
				],
			},
			{
				"role": "assistant",
				"content": "",
				"tool_calls": [
					{
						"id": "c1",
						"type": "function",
						"function": {"name": "get_company_info", "arguments": "{}"},
					},
					{
						"id": "c2",
						"type": "function",
						"function": {"name": "describe_doctype", "arguments": '{"doctype": "Item"}'},
					},
				],
			},
			{"role": "tool", "tool_call_id": "c1", "content": '{"company_name": "x"}'},
			{"role": "tool", "tool_call_id": "c2", "content": "{}"},
		]
		tools = [
			{
				"type": "function",
				"function": {
					"name": "get_company_info",
					"description": "d",
					"parameters": {"type": "object"},
				},
			}
		]
		request = to_anthropic_request("claude-opus-4-8", messages, tools)
		self.assertEqual(request["system"], "be brief")
		self.assertEqual([turn["role"] for turn in request["messages"]], ["user", "assistant", "user"])
		self.assertEqual(request["messages"][0]["content"][1]["source"]["media_type"], "image/png")
		self.assertEqual(request["messages"][1]["content"][1]["input"], {"doctype": "Item"})
		# Both tool results go back in one user turn
		self.assertEqual([b["tool_use_id"] for b in request["messages"][2]["content"]], ["c1", "c2"])
		self.assertEqual(request["tools"][0]["input_schema"], {"type": "object"})

	def test_response_conversion(self):
		from iran_erp.ai.anthropic import from_anthropic_response

		response = from_anthropic_response(
			{
				"id": "m1",
				"model": "claude-opus-4-8",
				"content": [
					{"type": "text", "text": "در حال جستجو"},
					{
						"type": "tool_use",
						"id": "t1",
						"name": "search_documents",
						"input": {"doctype": "Customer"},
					},
				],
				"stop_reason": "tool_use",
				"usage": {"input_tokens": 10, "output_tokens": 5},
			}
		)
		message = response["choices"][0]["message"]
		self.assertEqual(message["content"], "در حال جستجو")
		self.assertEqual(message["tool_calls"][0]["function"]["name"], "search_documents")
		self.assertEqual(message["tool_calls"][0]["function"]["arguments"], '{"doctype": "Customer"}')
		self.assertEqual(response["usage"]["total_tokens"], 15)
