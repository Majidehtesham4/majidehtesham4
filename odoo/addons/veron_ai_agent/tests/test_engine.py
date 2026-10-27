import io
import json
from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..services import providers, registry
from .common import AgentCase, FakeAdapter, answer, calls


@tagged("post_install", "-at_install")
class TestEngine(AgentCase):
	def test_role_library(self):
		templates = self.env["veron.ai.agent.template"].search([])
		self.assertGreaterEqual(len(templates), 35)
		self.assertEqual(len(templates.filtered(lambda t: t.category == "finance")), 14)
		# A role whose tools are not installed is not made
		missing = templates.filtered(lambda t: not t.available)[:1]
		if missing:
			wizard = self.env["veron.ai.activate.wizard"].with_user(self.manager).create({"template_id": missing.id,
				"authority_level": "1", "understood": True})
			with self.assertRaisesRegex(UserError, "Install"):
				wizard.action_create()
		template = self.env.ref("veron_ai_agent.role_sal_customer_summary")
		self.assertTrue(template.available, template.missing)
		wizard = self.env["veron.ai.activate.wizard"].with_user(self.manager).create({"template_id": template.id,
			"authority_level": "1", "company_ids": [(6, 0, self.company_a.ids)]})
		with self.assertRaises(UserError):
			wizard.action_create()
		wizard.understood = True
		agent = self.env["veron.ai.agent"].browse(wizard.action_create()["res_id"])
		self.assertFalse(agent.enabled, "a new agent waits for a manager to turn it on")
		self.assertTrue(agent.grant_ids)
		self.assertEqual(set(agent.grant_ids.mapped("level")), {"1"})

	def test_tool_names_in_persian(self):
		if not self.env["res.lang"]._lang_get("fa_IR"):
			self.skipTest("Persian is not installed")
		self.env["veron.ai.tool"]._sync()
		tool = self.env["veron.ai.tool"]._by_codes("records_search")
		self.assertEqual(tool.with_context(lang="fa_IR").name, "جست‌وجوی رکوردها")
		# The language model reads the tools in English
		self.assertTrue(registry.get("records_search").definition()["description"].startswith("Search Records."))

	def test_persian_conversation_and_records(self):
		agent = self.make_agent("1", ["records_search"])
		run = self.start(agent, text="مشتری‌های شرکت را فهرست کن", script=[
			calls(("records_search", {"model": "res.partner", "filters": [["name", "ilike", "مشتری"]], "fields": ["name"]})),
			answer("دو مشتری پیدا شد: **مشتری الف**"),
		])
		self.assertEqual(run.state, "done")
		self.assertIn("مشتری الف", run.output_html)
		self.assertIn("مشتری‌های شرکت", FakeAdapter.calls[0]["messages"][0]["text"])
		self.assertEqual(FakeAdapter.calls[0]["tools"], ["records_search"])
		self.assertIn(self.partner_a, self.env["res.partner"].browse(run.link_ids.mapped("res_id")))
		self.assertTrue(self.env["veron.ai.audit"].search([("run_id", "=", run.id), ("event", "=", "run_finished")]))
		self.assertEqual(run.usage, "10 / 5")

	def test_provider_errors_and_retry(self):
		agent = self.make_agent("1", ["records_search"], max_retries=1)
		FakeAdapter.error = providers.ProviderError("busy", retryable=True, kind="rate_limit")
		try:
			run = self.start(agent)
			self.assertEqual(run.state, "queued")
			self.assertEqual(run.retry_count, 1)
			self.assertTrue(run.next_attempt_at)
			run.next_attempt_at = fields.Datetime.now()
			self.env["veron.ai.run"]._cron_process()
			self.assertEqual(run.state, "failed")
			self.assertTrue(run.activity_ids, "the responsible person is told")
			self.assertEqual(self.provider.state, "error")
		finally:
			FakeAdapter.error = None

	def test_missing_key(self):
		provider = self.env["veron.ai.provider"].create({"name": "No key", "kind": "search", "adapter": "searxng"})
		self.assertFalse(provider.key_set)
		adapter = providers.Adapter({})
		with self.assertRaises(providers.ProviderError):
			adapter.secret()
		# The key is for administrators only, and never in the error
		with self.assertRaises(Exception):
			self.provider.with_user(self.manager).read(["api_key"])
		self.assertNotIn("1234567890abcdef", providers.ProviderError("failed with sk-test-1234567890abcdef").args[0])

	def test_no_model_runs_steps_only(self):
		self.provider.active = False
		agent = self.make_agent("1", ["records_aggregate"], llm_provider_id=False,
			playbook=json.dumps([{"tool": "records_aggregate", "args": {"model": "res.partner"}}]))
		run = self.start(agent, text="")
		self.assertEqual(run.state, "done")
		self.assertEqual(run.step_ids.decision, "allowed")
		self.assertEqual(FakeAdapter.calls, [])

	def test_action_not_done_twice_on_retry(self):
		agent = self.make_agent("3", ["activity_create"])
		args = {"model": "res.partner", "id": self.partner_a.id, "summary": "پیگیری"}
		run = self.start(agent, script=[calls(("activity_create", args))])
		retry = self.env["veron.ai.run"]._enqueue(agent, self.user, "retry", parent=run, text=run.input_text)
		FakeAdapter.script = [calls(("activity_create", args))]
		retry._execute()
		self.assertEqual(retry.step_ids.decision, "reused")
		self.assertEqual(len(self.partner_a.activity_ids), 1)

	def test_question_and_answer(self):
		agent = self.make_agent("1", ["request_human_input"])
		run = self.start(agent, script=[calls(("request_human_input", {"question": "نرخ بیمه ۱۴۰۵ تأیید شده چیست؟"}))])
		self.assertEqual(run.state, "waiting_info")
		question = run.approval_ids
		question.with_user(self.user).answer = "هنوز تأیید نشده"
		FakeAdapter.script = [answer("صبر می‌کنم")]
		question.with_user(self.user).action_answer()
		self.assertEqual(question.state, "answered")
		follow = run.child_run_ids
		self.assertEqual(follow.state, "done")
		self.assertIn("هنوز تأیید نشده", follow.input_text)

	def test_schedule(self):
		agent = self.make_agent("1", ["records_aggregate"], trigger_schedule=True, tz="Asia/Tehran",
			playbook=json.dumps([{"tool": "records_aggregate", "args": {"model": "res.partner"}}]))
		Schedule = self.env["veron.ai.schedule"]
		daily = Schedule.create({"agent_id": agent.id, "interval": "daily", "hour": 8.0})
		# 8:00 in Tehran is 4:30 UTC
		self.assertEqual(daily._next(datetime(2026, 10, 27, 5, 0)), datetime(2026, 10, 28, 4, 30))
		self.assertEqual(daily._next(datetime(2026, 10, 27, 4, 0)), datetime(2026, 10, 27, 4, 30))
		last = Schedule.create({"agent_id": agent.id, "interval": "monthly", "month_day": -1, "calendar": "shamsi", "hour": 20})
		# The last day of Aban 1405 is 30 Aban = 21 November 2026
		self.assertEqual(last._next(datetime(2026, 10, 27, 5, 0)).date(), datetime(2026, 11, 21).date())
		daily.next_run = fields.Datetime.now()
		last.next_run = datetime(2099, 1, 1)
		with patch.object(type(agent), "_in_working_hours", return_value=True):
			Schedule._cron_due()
		self.assertEqual(daily.last_run_id.state, "done")
		self.assertGreater(daily.next_run, fields.Datetime.now())
		# Outside the working hours it waits
		daily.next_run = fields.Datetime.now()
		with patch.object(type(agent), "_in_working_hours", return_value=False):
			Schedule._cron_due()
		self.assertEqual(len(agent.run_ids), 1)

	def test_sources(self):
		from PIL import Image

		Source = self.env["veron.ai.source"].with_user(self.user)
		with self.assertRaises(UserError):
			Source._from_upload("x.exe", b"MZ\x90\x00 program")
		buffer = io.BytesIO()
		Image.new("RGB", (30, 30), (0, 90, 200)).save(buffer, "JPEG")
		image = Source._from_upload("رسید.jpg", buffer.getvalue(), purpose="receipt")
		self.assertEqual((image.kind, image.mimetype), ("image", "image/jpeg"))
		self.assertTrue(image.sha256 and image.dhash)
		self.assertIn("no antivirus", image.scan)
		self.assertEqual(image._data(), buffer.getvalue())
		# Another user does not see it
		with self.assertRaises(Exception):
			image.with_user(self.other)._data()
		self.env["ir.config_parameter"].set_param("veron_ai_agent.max_upload_mb", 0)
		with self.assertRaises(UserError):
			Source._from_upload("big.jpg", buffer.getvalue())
		self.env["ir.config_parameter"].set_param("veron_ai_agent.max_upload_mb", 10)
		self.env["veron.ai.provider"].create({"name": "AV", "kind": "antivirus", "adapter": "test_fake"})
		with self.assertRaises(UserError):
			Source._from_upload("bad.pdf", b"%PDF-1.4\nEICAR test\n%%EOF")
		# Voice: transcribed, shown to the person, the audio not kept unless the company keeps it
		self.env["veron.ai.provider"].create({"name": "STT", "kind": "stt", "adapter": "test_fake"})
		voice = Source._from_upload("voice.webm", b"\x1aE\xdf\xa3" + b"\x00" * 64)
		self.assertEqual(voice.kind, "audio")
		self.assertIn("گزارش فروش", voice._transcribe(engine="ai"))
		self.assertEqual(voice.retention_until, fields.Date.context_today(voice))
		self.env["veron.ai.source"]._cron_cleanup()
		self.assertFalse(voice.sudo().attachment_id)
		self.assertTrue(voice.transcript)

	def test_audit_is_kept(self):
		agent = self.make_agent("1")
		event = self.env["veron.ai.audit"].search([("agent_id", "=", agent.id)], limit=1)
		self.assertTrue(event)
		with self.assertRaises(UserError):
			event.write({"description": "changed"})
		with self.assertRaises(Exception):
			event.with_user(self.manager).unlink()
