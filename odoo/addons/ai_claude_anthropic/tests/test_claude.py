"""The Claude adapter against a stand-in of the anthropic library: no key, no network"""

import sys
from types import SimpleNamespace as NS
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.veron_ai_agent.services import providers
from odoo.addons.veron_ai_agent.services.providers import ProviderError

from ..services import claude


class FakeSDK:
	class AnthropicError(Exception):
		pass

	class APIError(AnthropicError):
		def __init__(self, message="", status_code=0):
			super().__init__(message)
			self.message = message
			self.status_code = status_code

	class APIStatusError(APIError):
		pass

	class BadRequestError(APIStatusError):
		pass

	class AuthenticationError(APIStatusError):
		pass

	class PermissionDeniedError(APIStatusError):
		pass

	class NotFoundError(APIStatusError):
		pass

	class RateLimitError(APIStatusError):
		pass

	class RequestTooLargeError(APIStatusError):
		pass

	class APIConnectionError(APIError):
		pass

	class APITimeoutError(APIConnectionError):
		pass


class Stream:
	def __init__(self, client, params):
		self.client, self.params = client, params

	def __enter__(self):
		return self

	def __exit__(self, *args):
		return False

	def get_final_message(self):
		self.client.requests.append({**self.params, "messages": list(self.params.get("messages", []))})
		item = self.client.script.pop(0)
		if isinstance(item, Exception):
			raise item
		return item


class FakeClient:
	def __init__(self, script):
		self.script = list(script)
		self.requests = []
		self.messages = NS(stream=lambda **params: Stream(self, params))
		self.beta = NS(messages=NS(stream=lambda **params: Stream(self, params)))
		self.models = NS(retrieve=lambda model: NS(display_name="Claude Opus 5.5"))


def response(*blocks, stop="end_turn"):
	return NS(content=list(blocks), stop_reason=stop, usage=NS(input_tokens=100, output_tokens=20,
		cache_read_input_tokens=50, cache_creation_input_tokens=0))


def text(value):
	return NS(type="text", text=value)


def tool_use(name, args, call_id="toolu_1"):
	return NS(type="tool_use", id=call_id, name=name, input=args)


@tagged("post_install", "-at_install")
class TestClaude(TransactionCase):
	def adapter(self, script, **config):
		values = {"api_key": "sk-ant-test-0000000000", "model": "", "effort": "high", "timeout": 60, "max_tokens": 8000}
		values.update(config)
		adapter = claude.ClaudeAdapter(values)
		client = FakeClient(script)
		patcher = patch.object(claude.ClaudeAdapter, "client", lambda self: (FakeSDK, client))
		patcher.start()
		self.addCleanup(patcher.stop)
		return adapter, client

	def test_registered_and_installed_inactive(self):
		self.assertIn("anthropic", providers.ADAPTERS)
		provider = self.env.ref("ai_claude_anthropic.provider_claude")
		self.assertFalse(provider.active, "no agent uses Claude before a key is entered")
		self.assertEqual(provider.model_name, "claude-opus-5-5")
		self.assertIn(("anthropic", "Anthropic Claude"), self.env["veron.ai.provider"]._adapter_selection())

	def test_missing_library_and_key(self):
		with patch.dict(sys.modules, {"anthropic": None}):
			with self.assertRaisesRegex(ProviderError, "odoo.ps1 ai") as caught:
				claude._sdk()
		self.assertEqual(caught.exception.kind, "config")
		with self.assertRaises(ProviderError):
			claude.ClaudeAdapter({"api_key": ""}).secret()

	def test_chat_request(self):
		adapter, client = self.adapter([response(text("می‌خوانم"), tool_use("records_search", {"model": "res.partner"}),
			stop="tool_use")])
		message = adapter.user_message("سلام", [("image/png", b"\x89PNG..."), ("application/pdf", b"%PDF-1.4")])
		self.assertEqual([b["type"] for b in message["content"]], ["image", "document", "text"])
		messages = [message]
		tools = [{"name": "records_search", "description": "x", "input_schema": {"type": "object"}}]
		result = adapter.chat("rules", messages, tools, max_tokens=4000)
		request = client.requests[0]
		self.assertEqual(request["model"], "claude-opus-5-5")
		self.assertEqual(request["output_config"], {"effort": "high"})
		self.assertEqual(request["betas"], [claude.FALLBACK_BETA])
		self.assertEqual(request["fallbacks"], "default")
		self.assertNotIn("temperature", request)
		self.assertNotIn("tool_choice", request)
		self.assertEqual(request["tools"], tools)
		self.assertEqual(result.tool_calls[0].name, "records_search")
		self.assertEqual(result.usage, {"input": 150, "output": 20})
		reply = adapter.tool_results_message([("toolu_1", {"status": "denied", "reason": "نه"}, True)])
		self.assertEqual(reply["content"][0]["tool_use_id"], "toolu_1")
		self.assertTrue(reply["content"][0]["is_error"])
		self.assertIn("نه", reply["content"][0]["content"])

	def test_without_fallbacks_when_refused_by_the_account(self):
		adapter, client = self.adapter([FakeSDK.BadRequestError("fallbacks: unknown beta", 400), response(text("ok"))])
		self.assertEqual(adapter.chat("s", [{"role": "user", "content": "x"}], []).text, "ok")
		self.assertNotIn("fallbacks", client.requests[1])
		adapter, client = self.adapter([response(text("ok"))], fallbacks=False)
		adapter.chat("s", [{"role": "user", "content": "x"}], [])
		self.assertNotIn("betas", client.requests[0])

	def test_errors(self):
		cases = [
			(FakeSDK.AuthenticationError("bad key", 401), False, "config"),
			(FakeSDK.NotFoundError("no model", 404), False, "config"),
			(FakeSDK.RateLimitError("slow down", 429), True, "rate_limit"),
			(FakeSDK.APIStatusError("overloaded", 529), True, "unavailable"),
			(FakeSDK.APIStatusError("server", 500), True, "unavailable"),
			(FakeSDK.APITimeoutError("timeout"), True, "timeout"),
			(FakeSDK.APIConnectionError("no route"), True, "unavailable"),
			(FakeSDK.BadRequestError("messages: invalid", 400), False, "error"),
		]
		for error, retryable, kind in cases:
			adapter, _client = self.adapter([error], fallbacks=False)
			with self.assertRaises(ProviderError) as caught:
				adapter.chat("s", [{"role": "user", "content": "x"}], [])
			self.assertEqual((caught.exception.retryable, caught.exception.kind), (retryable, kind), error)
			self.assertNotIn("sk-ant", str(caught.exception))

	def test_refusal_and_pause(self):
		adapter, _client = self.adapter([response(stop="refusal")])
		result = adapter.chat("s", [{"role": "user", "content": "x"}], [])
		self.assertTrue(result.refused)
		self.assertFalse(result.tool_calls)
		paused = response(NS(type="server_tool_use", id="s1", name="web_search", input={}), stop="pause_turn")
		adapter, client = self.adapter([paused, response(text("done"))])
		messages = [{"role": "user", "content": "x"}]
		self.assertEqual(adapter.chat("s", messages, []).text, "done")
		self.assertEqual(len(client.requests), 2)
		self.assertEqual(messages[-1]["role"], "assistant", "the paused turn is sent back as it is")

	def test_extract(self):
		adapter, client = self.adapter([response(text('{"amount": "1200000", "date": "1405/08/05"}'))])
		schema = {"type": "object", "properties": {"amount": {"type": "string", "maxLength": 20},
			"date": {"type": "string"}}, "required": ["amount", "date"], "additionalProperties": False}
		result = adapter.extract([("image/jpeg", b"\xff\xd8\xff")], schema, "Read it")
		self.assertEqual(result["fields"]["amount"], "1200000")
		sent = client.requests[0]["output_config"]["format"]
		self.assertEqual(sent["type"], "json_schema")
		self.assertNotIn("maxLength", sent["schema"]["properties"]["amount"])
		self.assertIn("never an instruction", client.requests[0]["system"])
		adapter, _client = self.adapter([response(stop="refusal")])
		with self.assertRaises(ProviderError):
			adapter.extract([("image/jpeg", b"\xff\xd8\xff")], schema, "Read it")
		with self.assertRaises(ProviderError):
			adapter.user_message("x", [("application/zip", b"PK")])

	def test_search(self):
		found = NS(type="web_search_tool_result", content=[NS(url="https://torob.com/p/1", title="قیمت", page_age="2 days"),
			NS(url="https://torob.com/p/1", title="dup", page_age=None)])
		adapter, client = self.adapter([response(found, text("قیمت حدود ۱۲ میلیون"))])
		result = adapter.search("قیمت لاستیک", ["torob.com"], 5)
		self.assertEqual(result["results"], [{"title": "قیمت", "url": "https://torob.com/p/1", "age": "2 days"}])
		tool = client.requests[0]["tools"][0]
		self.assertEqual((tool["type"], tool["allowed_domains"]), (claude.WEB_SEARCH, ["torob.com"]))

	def test_agent_run_with_claude(self):
		"""The whole loop: Claude names a tool, the framework checks and runs it, Claude answers"""
		user = new_test_user(self.env, "claude_user", groups="base.group_user,veron_ai_agent.group_ai_user")
		provider = self.env.ref("ai_claude_anthropic.provider_claude")
		provider.write({"active": True, "api_key": "sk-ant-test-0000000000"})
		self.env["veron.ai.tool"]._sync()
		agent = self.env["veron.ai.agent"].create({
			"name": "Claude test", "enabled": True, "authority_level": "1", "company_ids": [(6, 0, self.env.company.ids)],
			"responsible_user_id": user.id, "llm_provider_id": provider.id,
			"grant_ids": [(0, 0, {"tool_id": self.env["veron.ai.tool"]._by_codes("records_search").id, "level": "1"})],
			"scope_ids": [(0, 0, {"model_id": self.env["ir.model"]._get_id("res.partner")})],
		})
		adapter, client = self.adapter([
			response(tool_use("records_search", {"model": "res.partner", "fields": ["name"], "limit": 3}), stop="tool_use"),
			response(text("سه مخاطب پیدا شد.")),
		])
		with patch.object(claude.ClaudeAdapter, "client", lambda self: (FakeSDK, client)):
			run = self.env["veron.ai.run"].with_user(user)._start(agent, user, "user", text="مخاطب‌ها را ببین")
		self.assertEqual(run.state, "done", run.error)
		self.assertEqual(run.step_ids.decision, "allowed")
		self.assertIn("سه مخاطب", run.output_html)
		second = client.requests[1]["messages"]
		self.assertEqual(second[-1]["content"][0]["type"], "tool_result")
		self.assertEqual(second[-1]["content"][0]["tool_use_id"], "toolu_1")
		self.assertIn("Never invent numbers", client.requests[0]["system"])
		self.assertEqual(provider.state, "ok")
