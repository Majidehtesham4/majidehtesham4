"""A fake provider the tests drive: it answers from a script, so the engine is tested without any service"""

from odoo.tests import TransactionCase, new_test_user

from ..services import providers


@providers.register("test_fake", ["llm", "vision", "stt", "antivirus"])
class FakeAdapter(providers.Adapter):
	label = "Test"
	script = []
	calls = []
	error = None

	def chat(self, system, messages, tools, max_tokens=4096):
		FakeAdapter.calls.append({"system": system, "messages": list(messages), "tools": [t["name"] for t in tools]})
		if FakeAdapter.error:
			raise FakeAdapter.error
		if not FakeAdapter.script:
			return providers.LLMResult(text="پایان", assistant_message={"role": "assistant"})
		return FakeAdapter.script.pop(0)

	def user_message(self, text, files=()):
		return {"role": "user", "text": text, "files": len(files)}

	def tool_results_message(self, results):
		return {"role": "user", "results": results}

	def transcribe(self, data, mimetype, language):
		return "سلام، گزارش فروش دیروز را بده"

	def extract(self, files, schema, instructions):
		return {"fields": {"amount": 1200000, "date": "2026-10-01"}, "text": "رسید"}

	def scan(self, data):
		return (b"EICAR" not in data), "test"


def answer(text):
	return providers.LLMResult(text=text, assistant_message={"role": "assistant", "text": text}, usage={"input": 10, "output": 5})


def calls(*items):
	"""A model turn calling tools: items are (name, input)"""
	return providers.LLMResult(tool_calls=[providers.ToolCall(f"c{i}", name, args) for i, (name, args) in enumerate(items)],
		assistant_message={"role": "assistant", "calls": items}, stop_reason="tool_use")


class AgentCase(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notrack=True, lang="en_US"))
		FakeAdapter.script, FakeAdapter.calls, FakeAdapter.error = [], [], None
		cls.company_a = cls.env.company
		cls.company_b = cls.env["res.company"].create({"name": "شرکت ب"})
		cls.manager = new_test_user(cls.env, "ai_manager", groups="base.group_user,veron_ai_agent.group_ai_manager",
			company_ids=[(6, 0, (cls.company_a | cls.company_b).ids)], company_id=cls.company_a.id)
		cls.user = new_test_user(cls.env, "ai_user", groups="base.group_user,veron_ai_agent.group_ai_user,base.group_partner_manager",
			company_ids=[(6, 0, cls.company_a.ids)], company_id=cls.company_a.id)
		cls.other = new_test_user(cls.env, "ai_other", groups="base.group_user,veron_ai_agent.group_ai_user",
			company_ids=[(6, 0, cls.company_a.ids)], company_id=cls.company_a.id)
		cls.partner_a = cls.env["res.partner"].create({"name": "مشتری الف", "email": "a@example.com",
			"company_id": cls.company_a.id})
		cls.partner_b = cls.env["res.partner"].create({"name": "مشتری ب", "company_id": cls.company_b.id})
		# The providers of the database (a key someone connected) take no part in the tests
		cls.env["veron.ai.provider"].search([]).write({"active": False})
		cls.provider = cls.env["veron.ai.provider"].create({"name": "Fake", "kind": "llm", "adapter": "test_fake",
			"is_default": True, "api_key": "sk-test-123456789"})
		cls.env["veron.ai.tool"]._sync()

	def setUp(self):
		super().setUp()
		FakeAdapter.script, FakeAdapter.calls, FakeAdapter.error = [], [], None

	def make_agent(self, level="1", tools=(), **values):
		Tool = self.env["veron.ai.tool"]
		grants = []
		for code in tools:
			code, extra = code if isinstance(code, tuple) else (code, {})
			grants.append((0, 0, {"tool_id": Tool._by_codes(code).id, "level": level, **extra}))
		vals = {
			"name": values.pop("name", "عامل آزمایشی"), "enabled": True, "authority_level": level,
			"company_ids": [(6, 0, (self.company_a | self.company_b).ids)], "company_id": self.company_a.id,
			"responsible_user_id": self.user.id, "user_ids": [(6, 0, self.user.ids)],
			"grant_ids": grants, "llm_provider_id": self.provider.id,
			"scope_ids": [(0, 0, {"model_id": self.env["ir.model"]._get_id("res.partner")})],
		}
		vals.update(values)
		return self.env["veron.ai.agent"].create(vals)

	def start(self, agent, text="گزارش بده", user=None, script=()):
		FakeAdapter.script = list(script)
		user = user or self.user
		return self.env["veron.ai.run"].with_user(user)._start(agent, user, "user", text=text)
