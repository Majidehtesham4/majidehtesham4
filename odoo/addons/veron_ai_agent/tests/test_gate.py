from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import AgentCase, calls


@tagged("post_install", "-at_install")
class TestGate(AgentCase):
	def _step(self, run, code):
		return run.step_ids.filtered(lambda s: s.tool_code == code)[-1:]

	def test_read_stays_in_scope_and_company(self):
		agent = self.make_agent("1", ["records_search"])
		run = self.start(agent, script=[calls(("records_search", {"model": "res.partner", "fields": ["name"], "limit": 80})),
			calls(("records_search", {"model": "res.users", "fields": ["login"]}))])
		names = [r["name"] for r in self._step(run, "records_search")[0].output_json and __import__("json").loads(
			run.step_ids[0].output_json)["records"]]
		self.assertIn("مشتری الف", names)
		# The user is only in company A: the agent sees nothing of company B, even though it is the agent's company
		self.assertNotIn("مشتری ب", names)
		self.assertEqual(run.step_ids[1].decision, "denied", "res.users is not in the agent's data")
		self.assertEqual(run.state, "done_warning")

	def test_fields_outside_scope_refused(self):
		agent = self.make_agent("1", ["records_search"])
		agent.scope_ids.field_ids = self.env["ir.model.fields"]._get("res.partner", "name")
		run = self.start(agent, script=[calls(("records_search", {"model": "res.partner", "fields": ["email"]})),
			calls(("records_search", {"model": "res.partner", "filters": [["email", "ilike", "a"]]}))])
		self.assertEqual(run.step_ids.mapped("decision"), ["denied", "denied"])

	def test_invalid_arguments_refused(self):
		agent = self.make_agent("1", ["records_search"])
		run = self.start(agent, script=[calls(("records_search", {"model": "res.partner", "sql": "select 1"})),
			calls(("not_a_tool", {}))])
		self.assertEqual(run.step_ids.mapped("decision"), ["failed", "denied"])

	def test_levels(self):
		args = {"model": "res.partner", "id": self.partner_a.id, "summary": "پیگیری"}
		results = {}
		for level in "1234":
			agent = self.make_agent(level, ["activity_create"], name=f"L{level}")
			run = self.start(agent, script=[calls(("activity_create", args))])
			results[level] = run.step_ids[0].decision
		self.assertEqual(results, {"1": "denied", "2": "suggestion", "3": "allowed", "4": "allowed"})

	def test_sensitive_always_waits(self):
		args = {"partner_id": self.partner_a.id, "channel": "email", "body": "سلام"}
		for level, expected in (("1", "denied"), ("2", "suggestion"), ("3", "approval"), ("4", "approval")):
			agent = self.make_agent(level, ["notify_external"], name=f"S{level}")
			run = self.start(agent, script=[calls(("notify_external", args))])
			self.assertEqual(run.step_ids[0].decision, expected, level)
		# Automatic without an explicit rule still waits
		agent = self.make_agent("4", [("notify_external", {"auto_execute": True})], name="auto")
		run = self.start(agent, script=[calls(("notify_external", args))])
		self.assertEqual(run.step_ids[0].decision, "approval")
		self.assertEqual(run.state, "waiting_approval")
		# With a manager's explicit rule it acts, within it
		agent.grant_ids.with_user(self.manager).write({"sensitive_rule": True, "rule_note": "یادآوری پرداخت"})
		run = self.start(agent, script=[calls(("notify_external", args))])
		self.assertEqual(run.step_ids[0].decision, "allowed")
		self.assertEqual(agent.grant_ids.rule_set_by, self.manager)

	def test_amount_limit(self):
		agent = self.make_agent("3", ["activity_create"], max_amount=100)
		tool = __import__("odoo.addons.veron_ai_agent.services.registry", fromlist=["get"]).get("activity_create")
		from ..services.registry import Plan

		env = agent._run_env(self.user)
		self.assertEqual(agent._decide(tool, Plan(summary="x", amount=50), env)[0], "allowed")
		self.assertEqual(agent._decide(tool, Plan(summary="x", amount=500), env)[0], "approval")
		self.assertEqual(agent._decide(tool, Plan(summary="x", company_ids=[self.company_b.id]), env)[0], "denied")

	def test_approval_by_a_person_only(self):
		agent = self.make_agent("3", ["notify_external"])
		run = self.start(agent, script=[calls(("notify_external", {"partner_id": self.partner_a.id, "channel": "email",
			"body": "یادآوری"}))])
		approval = run.approval_ids
		self.assertEqual(approval.state, "pending")
		# Someone not named on it, a service user, or anything inside a run may not decide
		with self.assertRaises(AccessError):
			approval.with_user(self.other).action_approve()
		self.other.veron_ai_service_user = True
		self.assertFalse(approval._may_decide(self.other))
		self.assertFalse(approval.with_context(veron_ai_run_id=run.id)._may_decide(self.user))
		count = len(self.partner_a.message_ids)
		approval.with_user(self.user).action_approve()
		self.assertEqual(approval.state, "executed", approval.result_json)
		self.assertEqual(approval.decided_by, self.user)
		self.assertGreater(len(self.partner_a.message_ids), count)
		self.assertEqual(run.state, "done")
		with self.assertRaises(UserError):
			approval.with_user(self.user).action_approve()

	def test_run_cannot_change_agents(self):
		agent = self.make_agent("4")
		with self.assertRaises(UserError):
			agent.with_context(veron_ai_run_id=1).write({"authority_level": "4", "max_amount": 0})
		with self.assertRaises(UserError):
			agent.grant_ids.with_context(veron_ai_run_id=1).create({"agent_id": agent.id,
				"tool_id": self.env["veron.ai.tool"]._by_codes("records_search").id, "level": "4"})

	def test_who_may_use(self):
		agent = self.make_agent("1", ["records_search"])
		with self.assertRaises(AccessError):
			self.env["veron.ai.run"].with_user(self.other)._start(agent, self.other, "user", text="x")
		agent.enabled = False
		with self.assertRaises(UserError):
			self.start(agent)

	def test_supervisor_only_tools(self):
		worker = self.make_agent("1", ["records_search"], name="کارگر")
		plain = self.make_agent("3", ["delegate_task"], name="ساده")
		run = self.start(plain, script=[calls(("delegate_task", {"agent": "کارگر", "title": "کار", "instructions": "بخوان"}))])
		self.assertEqual(run.step_ids[0].decision, "denied")
		boss = self.make_agent("3", ["delegate_task", "review_task"], name="ناظر", is_supervisor=True,
			delegate_agent_ids=[(6, 0, worker.ids)])
		run = self.start(boss, script=[
			calls(("delegate_task", {"agent": "بیگانه", "title": "کار", "instructions": "بخوان"})),
			calls(("delegate_task", {"agent": "کارگر", "title": "کار", "instructions": "بخوان"})),
		])
		self.assertEqual(run.step_ids.mapped("decision"), ["denied", "allowed"])
		task = self.env["veron.ai.task"].search([("parent_run_id", "=", run.id)])
		self.assertEqual(task.result_run_id.run_user_id, self.user, "a delegated task has the same rights")
		self.assertEqual(task.state, "done")
