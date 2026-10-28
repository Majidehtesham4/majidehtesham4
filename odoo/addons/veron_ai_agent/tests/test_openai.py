"""The OpenAI-format adapter (ChatGPT, Groq, OpenRouter) and several keys, against a stand-in of the HTTP service"""

import json
from unittest.mock import patch

from odoo.tests import tagged

from ..services import openai_chat, providers
from .common import AgentCase


class Response:
	def __init__(self, status, data=None):
		self.status_code = status
		self._data = data or {}
		self.text = json.dumps(self._data)
		self.content = self.text.encode()

	def json(self):
		return self._data


def completion(content="", calls=(), finish="stop"):
	message = {"role": "assistant", "content": content, "reasoning": "hidden"}
	if calls:
		message["tool_calls"] = [{"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
			for i, (name, args) in enumerate(calls)]
		finish = "tool_calls"
	return Response(200, {"choices": [{"message": message, "finish_reason": finish}],
		"usage": {"prompt_tokens": 30, "completion_tokens": 7}})


class Http:
	"""Answers in turn, and remembers the key and the body of each request"""

	def __init__(self, *answers):
		self.answers = list(answers)
		self.requests = []

	def __call__(self, method, url, timeout=None, headers=None, json=None, **kwargs):
		self.requests.append({"method": method, "url": url, "key": (headers or {}).get("Authorization", "")[7:], "json": json})
		return self.answers.pop(0)


@tagged("post_install", "-at_install")
class TestOpenAIFormat(AgentCase):
	def adapter(self, keys=("k1",), base="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile"):
		return openai_chat.OpenAIChat({"api_key": keys[0], "api_keys": list(keys), "base_url": base, "model": model,
			"timeout": 30, "max_tokens": 1000})

	def test_keys_stand_in_for_each_other(self):
		http = Http(Response(429), Response(401), completion("سلام"))
		with patch.object(providers.requests, "request", http):
			result = self.adapter(("k1", "k2", "k3")).chat("rules", [{"role": "user", "content": "سلام"}], [])
		self.assertEqual(result.text, "سلام")
		self.assertEqual([r["key"] for r in http.requests], ["k1", "k2", "k3"])
		http = Http(Response(429), Response(429), Response(429))
		with patch.object(providers.requests, "request", http), self.assertRaises(providers.ProviderError) as caught:
			self.adapter(("k1", "k2", "k3")).chat("rules", [{"role": "user", "content": "x"}], [])
		self.assertTrue(caught.exception.retryable)
		self.assertIn("3 keys", str(caught.exception))
		# Another failure is not hidden by trying the other keys
		http = Http(Response(400, {"error": "bad"}))
		with patch.object(providers.requests, "request", http), self.assertRaises(providers.ProviderError):
			self.adapter(("k1", "k2")).chat("rules", [{"role": "user", "content": "x"}], [])
		self.assertEqual(len(http.requests), 1)

	def test_provider_rotates_its_keys(self):
		provider = self.env["veron.ai.provider"].create({"name": "Groq", "kind": "llm", "adapter": "openai_chat",
			"model_name": "m", "api_key": "k1", "extra_keys": "k2, k3  k4"})
		self.assertEqual(provider.key_count, 4)
		firsts = []
		for _i in range(4):
			firsts.append(provider._config()["api_keys"][0])
		self.assertEqual(firsts, ["k1", "k2", "k3", "k4"])
		self.assertNotIn("k2", json.dumps(provider.with_user(self.manager).read(["name", "key_count"])))

	def test_tool_call_and_payload(self):
		http = Http(completion(calls=[("records_search", {"model": "res.partner"})]))
		tools = [{"name": "records_search", "description": "Search", "input_schema": {"type": "object"}}]
		files = [("image/png", b"\x89PNG"), ("application/pdf", b"%PDF-1.4")]
		# A model that reads only text is never sent the photo: the request would fail
		self.assertIsInstance(self.adapter().user_message("x", files)["content"], str)
		adapter = self.adapter(model="meta-llama/llama-4-scout-17b-16e-instruct")
		messages = [adapter.user_message("مشتری‌ها", files)]
		with patch.object(providers.requests, "request", http):
			result = adapter.chat("rules", messages, tools, max_tokens=500)
		body = http.requests[0]["json"]
		self.assertEqual(http.requests[0]["url"], "https://api.groq.com/openai/v1/chat/completions")
		self.assertEqual(body["max_completion_tokens"], 500)
		self.assertEqual(body["tools"][0]["function"]["name"], "records_search")
		self.assertEqual(body["messages"][0], {"role": "system", "content": "rules"})
		self.assertEqual(body["messages"][1]["content"][1]["type"], "image_url")
		self.assertEqual(result.tool_calls[0].input, {"model": "res.partner"})
		self.assertNotIn("reasoning", result.assistant_message)
		self.assertEqual(result.usage, {"input": 30, "output": 7})
		replies = adapter.tool_results_message([("call_0", {"count": 2}, False)])
		self.assertEqual(replies, [{"role": "tool", "tool_call_id": "call_0", "content": '{"count": 2}'}])
		# OpenRouter takes max_tokens
		http = Http(completion("ok"))
		with patch.object(providers.requests, "request", http):
			self.adapter(base="https://openrouter.ai/api/v1").chat("s", [{"role": "user", "content": "x"}], [], max_tokens=9)
		self.assertEqual(http.requests[0]["json"]["max_tokens"], 9)

	def test_agent_run_with_groq(self):
		provider = self.env["veron.ai.provider"].create({"name": "Groq", "kind": "llm", "adapter": "openai_chat",
			"base_url": "https://api.groq.com/openai/v1", "model_name": "llama-3.3-70b-versatile", "api_key": "k1",
			"extra_keys": "k2"})
		agent = self.make_agent("1", ["records_search"], llm_provider_id=provider.id)
		http = Http(Response(429), completion(calls=[("records_search", {"model": "res.partner", "fields": ["name"]})]),
			completion("دو مشتری هست."))
		with patch.object(providers.requests, "request", http):
			run = self.env["veron.ai.run"].with_user(self.user)._start(agent, self.user, "user", text="مشتری‌ها؟")
		self.assertEqual(run.state, "done", run.error)
		self.assertIn("دو مشتری", run.output_html)
		second = http.requests[2]["json"]["messages"]
		self.assertEqual(second[-1]["role"], "tool")
		self.assertEqual(second[-2]["tool_calls"][0]["function"]["name"], "records_search")

	def test_extract_and_check(self):
		http = Http(completion('{"amount": "1200000", "date": "1405/08/05"}'))
		schema = {"type": "object", "properties": {"amount": {"type": "string"}, "date": {"type": "string"},
			"vendor": {"type": "string"}}}
		with patch.object(providers.requests, "request", http):
			result = self.adapter().extract([("image/jpeg", b"\xff\xd8\xff")], schema, "Read it")
		self.assertEqual(result["fields"], {"amount": "1200000", "date": "1405/08/05", "vendor": ""})
		self.assertEqual(http.requests[0]["json"]["response_format"], {"type": "json_object"})
		http = Http(Response(200, {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"}]}))
		with patch.object(providers.requests, "request", http):
			message = self.adapter().check()
		self.assertIn("2", self.env._(message))
		self.assertEqual(http.requests[0]["method"], "get")
		http = Http(Response(200, {"data": [{"id": "other"}]}))
		with patch.object(providers.requests, "request", http), self.assertRaises(providers.ProviderError):
			self.adapter().check()

	def test_speech_to_text_uses_the_keys(self):
		stt = providers.OpenAICompatibleHttp({"api_key": "k1", "api_keys": ["k1", "k2"],
			"base_url": "https://api.groq.com/openai/v1", "model": "whisper-large-v3"})
		http = Http(Response(429), Response(200, {"text": " سلام "}))
		with patch.object(providers.requests, "request", http):
			self.assertEqual(stt.transcribe(b"\x1aE\xdf\xa3", "audio/webm", "fa"), "سلام")
		self.assertEqual([r["key"] for r in http.requests], ["k1", "k2"])
