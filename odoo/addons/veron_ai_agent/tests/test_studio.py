"""Skills, knowledge sources, triggers and default prompts, as in Odoo's AI app"""

import base64
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..services import knowledge
from .common import AgentCase


@tagged("post_install", "-at_install")
class TestKnowledgeText(TransactionCase):
	def test_persian_search(self):
		passages = [(1, "شرایط بازگشت کالا: مشتری تا هفت روز پس از خرید می‌تواند کالای سالم را برگرداند."),
			(2, "ساعات کاری فروشگاه از شنبه تا پنجشنبه، ۹ صبح تا ۸ شب است."),
			(3, "هزینه ارسال برای خریدهای بالای ۵ میلیون ریال رایگان است.")]
		self.assertEqual(knowledge.rank("چند روز وقت دارم کالا را برگردانم؟", passages)[0][0], 1)
		self.assertEqual(knowledge.rank("ساعت كاري فروشگاه", passages)[0][0], 2, "Arabic letters read as Persian")
		self.assertFalse(knowledge.rank("هواپیما", passages))

	def test_chunks(self):
		text = "\n\n".join(f"بند {i}: " + "متن نمونه " * 60 for i in range(6))
		pieces = knowledge.chunks(text)
		self.assertGreater(len(pieces), 3)
		self.assertTrue(all(len(p) <= knowledge.CHUNK + knowledge.OVERLAP + 10 for p in pieces))

	def test_private_links_refused(self):
		for url in ("http://127.0.0.1:8069/web", "http://10.0.0.5/", "file:///etc/passwd", "http://localhost/"):
			with self.assertRaises(knowledge.SourceError):
				knowledge.check_public(url)


@tagged("post_install", "-at_install")
class TestStudio(AgentCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env["veron.ai.skill"]._setup_builtin()

	def setUp(self):
		super().setUp()
		self.agent = self.make_agent(level="3")

	def test_builtin_skills(self):
		skills = self.env["veron.ai.skill"].search([("code", "!=", False)])
		self.assertIn("records", skills.mapped("code"))
		self.env["veron.ai.skill"]._setup_builtin()
		self.assertEqual(len(self.env["veron.ai.skill"].search([("code", "!=", False)])), len(skills), "made once")

	def test_skill_brings_its_tools(self):
		agent = self.agent
		skill = self.env["veron.ai.skill"].search([("code", "=", "records")])
		agent.skill_ids = [(4, skill.id)]
		granted = agent.grant_ids.filtered("active").mapped("tool_id.code")
		for code in ("records_search", "record_read"):
			self.assertIn(code, granted)
		grant = agent.grant_ids.filtered(lambda g: g.tool_id.code == "records_search")
		self.assertLessEqual(int(grant.level), int(agent.authority_level), "at the agent's own authority")
		agent.skill_ids = [(5, 0, 0)]
		self.assertFalse(agent.grant_ids.filtered(lambda g: g.active and g.from_skill and g.tool_id.code == "records_search"),
			"turned off with the skill")
		agent.use_web_search = True
		self.assertIn("web_search", agent.grant_ids.filtered("active").mapped("tool_id.code"))

	def test_knowledge_sources(self):
		agent = self.agent
		text = "سیاست بازگشت کالا: کالای سالم تا هفت روز پس از خرید پس گرفته می‌شود.\n\nارسال رایگان نیست."
		wizard = self.env["veron.ai.knowledge.add"].create({"agent_id": agent.id})
		wizard.action_choose_file()
		wizard.write({"file": base64.b64encode(text.encode()), "filename": "policy.txt"})
		wizard.action_save()
		source = agent.knowledge_ids
		self.assertEqual((source.state, source.kind), ("indexed", "file"))
		self.assertTrue(source.chunk_ids)
		self.assertIn("knowledge_sources", agent.grant_ids.filtered("active").mapped("tool_id.code"))
		found = self.env["veron.ai.knowledge"]._find_passages(agent, "بازگشت کالا چند روز است")
		self.assertIn("هفت روز", found[0]["passage"])
		bad = self.env["veron.ai.knowledge"].create({"name": "x", "kind": "link", "url": "http://127.0.0.1/", "agent_ids": [(4, agent.id)]})
		self.assertEqual(bad.state, "failed")
		self.assertTrue(bad.error)
		agent.restrict_to_sources = True
		run = self.env["veron.ai.run"].sudo().create(self.env["veron.ai.run"]._values(agent, self.env.user, "user",
			text="بازگشت کالا چند روز است"))
		self.assertIn("Answer only from the passages", run._system_prompt())
		self.assertIn("هفت روز", run._knowledge_passages()[0]["passage"])
		# Without AI, the built-in assistant answers from the sources what it does not understand otherwise
		from ..models.ai_internal import Brain
		html = Brain(run, self.env)._not_understood([])
		self.assertIn("هفت روز", html)

	def test_link_source(self):
		page = "<html><body><h1>راهنما</h1><p>تحویل کالا در تهران یک روزه است.</p><script>x()</script></body></html>"

		class Response:
			status_code = 200
			is_redirect = is_permanent_redirect = False
			headers = {"content-type": "text/html"}
			encoding = "utf-8"

			def raise_for_status(self):
				pass

			def iter_content(self, size):
				yield page.encode()

		with patch.object(knowledge, "check_public", return_value=True), patch("requests.get", return_value=Response()):
			source = self.env["veron.ai.knowledge"].create({"name": "راهنما", "kind": "link", "url": "https://example.ir/help",
				"agent_ids": [(4, self.agent.id)]})
		self.assertEqual(source.state, "indexed")
		self.assertIn("یک روزه", source.chunk_ids[0].text)
		self.assertNotIn("x()", source.chunk_ids[0].text)

	def test_triggers(self):
		agent = self.agent
		agent.sudo().enabled = True
		partner_model = self.env["ir.model"]._get("res.partner")
		wizard = self.env["veron.ai.trigger.add"].create({"agent_id": agent.id})
		wizard.action_create()
		wizard.write({"model_id": partner_model.id, "input_text": "این مشتری تازه را بررسی کن"})
		wizard.action_save()
		trigger = agent.trigger_ids
		self.assertEqual(trigger.automation_id.trigger, "on_create")
		self.assertTrue(trigger.automation_id.active)
		partner = self.env["res.partner"].create({"name": "مشتری تازه"})
		run = self.env["veron.ai.run"].sudo().search([("agent_id", "=", agent.id)], order="id desc", limit=1)
		self.assertIn("مشتری تازه", run.input_text)
		self.assertEqual(run.state, "queued", "done by the queue, not inside the save of the record")
		self.assertFalse(trigger._fire(partner), "not twice in a row for the same record")
		agent.sudo().enabled = False
		self.assertFalse(trigger.automation_id.active, "off with its agent")
		schedule = self.env["veron.ai.trigger"].create({"agent_id": agent.id, "kind": "schedule", "input_text": "گزارش روزانه"})
		self.assertTrue(schedule.schedule_id)
		self.assertTrue(agent.trigger_schedule)
		date_field = self.env["ir.model.fields"]._get("res.partner", "write_date")
		dated = self.env["veron.ai.trigger"].create({"agent_id": agent.id, "kind": "date", "model_id": partner_model.id,
			"date_field_id": date_field.id, "delay": 2, "delay_unit": "day", "input_text": "پیگیری"})
		self.assertEqual((dated.automation_id.trigger, dated.automation_id.trg_date_range), ("on_time", 2))
		automation = dated.automation_id
		dated.unlink()
		self.assertFalse(automation.exists())

	def test_default_prompts(self):
		rule = self.env["veron.ai.prompt.rule"].create({"name": "فاکتورها", "instructions": "روی فاکتورها مبلغ را با سفارش مقایسه کن.",
			"model_ids": [(6, 0, self.env["ir.model"]._get("res.partner").ids)],
			"button_ids": [(0, 0, {"title": "خلاصه مشتری", "prompt": "خلاصه این مشتری را بگو"})]})
		self.assertEqual(self.env["veron.ai.prompt.rule"].veron_prompts("res.partner")[0]["title"], "خلاصه مشتری",
			"the prompts of the page come before those of every page")
		everywhere = self.env.ref("veron_ai_agent.prompt_rule_everywhere").button_ids.mapped("title")
		self.assertEqual([p["title"] for p in self.env["veron.ai.prompt.rule"].veron_prompts("res.users")], everywhere)
		values = self.env["veron.ai.run"]._values(self.agent, self.env.user, "chat", text="سلام",
			page={"model": "res.partner", "res_id": 1, "title": "x"})
		run = self.env["veron.ai.run"].sudo().create(values)
		self.assertIn(rule.instructions, run._system_prompt())

	def test_response_style(self):
		self.agent.response_style = "rigorous"
		run = self.env["veron.ai.run"].sudo().create(self.env["veron.ai.run"]._values(self.agent, self.env.user, "user", text="x"))
		self.assertIn("precision", run._system_prompt())
		self.assertEqual(self.agent._temperature(), 0.1)
