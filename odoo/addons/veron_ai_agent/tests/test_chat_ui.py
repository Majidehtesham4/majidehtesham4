"""The agent's page and the chat window: the person's conversations, a new chat, the options of a conversation, and
the agent's panel that only a manager of the agents changes"""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import AgentCase, FakeAdapter, answer


@tagged("post_install", "-at_install")
class TestChatPage(AgentCase):
	def setUp(self):
		super().setUp()
		self.agent = self.make_agent(level="1", tools=["records_search", "web_search"], description="یک ایجنت آزمایشی")
		self.Chat = self.env["veron.ai.conversation"].with_user(self.user)

	def send(self, conversation_id, text, script=("پاسخ",)):
		FakeAdapter.script = [answer(t) for t in script]
		return self.Chat.veron_chat_send(conversation_id, text, [], {}, "ai")

	def test_new_chat_and_list(self):
		first = self.Chat.veron_chat_start(self.agent.id)
		self.assertFalse(first["previous_id"])
		again = self.Chat.veron_chat_start(self.agent.id)
		self.assertEqual(again["conversation_id"], first["conversation_id"], "an empty chat is used again")
		self.assertFalse(self.Chat.veron_chat_conversations(self.agent.id), "an empty chat is not listed")

		self.send(first["conversation_id"], "گزارش فروش دیروز را بده")
		listed = self.Chat.veron_chat_conversations(self.agent.id)
		self.assertEqual([c["id"] for c in listed], [first["conversation_id"]])
		self.assertEqual(listed[0]["title"], "گزارش فروش دیروز را بده")
		self.assertTrue(listed[0]["snippet"].startswith("پاسخ"), "the answer's words, without its markup")
		self.assertFalse(listed[0]["unread"], "seen by the person who asked")

		second = self.Chat.veron_chat_start(self.agent.id)
		self.assertNotEqual(second["conversation_id"], first["conversation_id"])
		self.assertEqual(second["previous_id"], first["conversation_id"], "the previous chat may be resumed")
		self.assertEqual(len(self.Chat.veron_chat_conversations(self.agent.id, "فروش")), 1)
		self.assertFalse(self.Chat.veron_chat_conversations(self.agent.id, "هواپیما"))

		loaded = self.Chat.veron_chat_load(first["conversation_id"])
		self.assertEqual([m["role"] for m in loaded["messages"]], ["user", "agent"])
		self.assertIn("steps", loaded["messages"][1])

	def test_someone_elses_conversation(self):
		started = self.Chat.veron_chat_start(self.agent.id)
		Other = self.env["veron.ai.conversation"].with_user(self.manager)
		for call in (lambda: Other.veron_chat_load(started["conversation_id"]),
				lambda: Other.veron_chat_options(started["conversation_id"], {"show_steps": True})):
			with self.assertRaises(AccessError):
				call()

	def test_web_search_off(self):
		started = self.Chat.veron_chat_start(self.agent.id)
		self.send(started["conversation_id"], "سلام")
		self.assertIn("web_search", FakeAdapter.calls[-1]["tools"])
		options = self.Chat.veron_chat_options(started["conversation_id"], {"web_search": False, "think_longer": True,
			"something": True})
		self.assertEqual(options, {"web_search": False, "show_steps": False, "think_longer": True})
		self.send(started["conversation_id"], "دوباره")
		self.assertNotIn("web_search", FakeAdapter.calls[-1]["tools"], "the person turned the web search off")
		self.assertIn("records_search", FakeAdapter.calls[-1]["tools"])

	def test_think_longer(self):
		provider = self.provider.with_context(veron_ai_think=True)
		self.assertGreaterEqual(provider._answer_tokens(), 16000)
		self.assertEqual(provider._config()["effort"], "xhigh")
		self.assertEqual(self.provider._answer_tokens(), self.provider.max_tokens or 8000)

	def test_panel(self):
		Agent = self.env["veron.ai.agent"]
		panel = Agent.with_user(self.user).veron_agent_panel(self.agent.id)
		self.assertEqual(panel["name"], self.agent.name)
		self.assertFalse(panel["can_edit"], "a user reads the panel")
		self.assertEqual([t["field"] for t in panel["tools"]], ["use_image", "use_web_search", "self_update"])
		with self.assertRaises(AccessError):
			Agent.with_user(self.user).veron_agent_panel_write(self.agent.id, {"instructions": "x"})
		with self.assertRaises(AccessError):
			Agent.with_user(self.other).veron_agent_panel(self.agent.id)

		skill = self.env["veron.ai.skill"].create({"name": "مهارت آزمایشی"})
		sub = self.make_agent(name="زیرایجنت")
		panel = Agent.with_user(self.manager).veron_agent_panel_write(self.agent.id, {
			"instructions": "# کار\n- فقط پیش‌نویس بساز", "add_skill": skill.id, "add_subagent": sub.id,
			"authority_level": "4", "enabled": False})
		self.assertTrue(panel["can_edit"])
		self.assertEqual([s["id"] for s in panel["skills"]], [skill.id])
		self.assertEqual([s["id"] for s in panel["subagents"]], [sub.id])
		self.assertTrue(self.agent.is_supervisor, "an agent with subagents supervises them")
		self.assertEqual(self.agent.authority_level, "1", "the panel changes only its own fields")
		self.assertTrue(self.agent.enabled)
		self.assertIn("<h5>کار</h5>", panel["instructions_html"])
		self.assertIn("<li>فقط پیش‌نویس بساز</li>", panel["instructions_html"])
		panel = Agent.with_user(self.manager).veron_agent_panel_write(self.agent.id, {"remove_skill": skill.id,
			"remove_subagent": sub.id})
		self.assertFalse(panel["skills"] or panel["subagents"])

	def test_instructions_escaped(self):
		self.agent.instructions = "<script>alert(1)</script>\n- <b>x</b>"
		html = self.agent._instructions_html()
		self.assertNotIn("<script>", html)
		self.assertNotIn("<b>", html)
