import json

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.veron_ai_agent.services import registry
from odoo.addons.veron_ai_agent.tests.common import FakeAdapter, answer, calls

# Mehr and Shahrivar 1405
MEHR = ("2026-09-23", "2026-10-22")
TOOLS = ["payroll_inputs_check", "payslip_drafts_compute", "payroll_compare_previous", "payslip_pdf_prepare", "request_human_input"]
WAGE = 600000000


@tagged("post_install", "-at_install")
class TestPayrollAgent(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notrack=True))
		cls.manager = new_test_user(cls.env, "pay_manager", groups="base.group_user,payroll.group_payroll_manager,"
			"veron_ai_agent.group_ai_user,hr.group_hr_user,account.group_account_invoice")
		cls.worker_user = new_test_user(cls.env, "pay_worker", groups="base.group_user")
		cls.colleague = new_test_user(cls.env, "pay_colleague", groups="base.group_user")
		cls.rates = cls.env.ref("veron_payroll_iran.payroll_year_1405")
		structure = cls.env.ref("veron_payroll_iran.structure_iran")
		cls.employees = cls.env["hr.employee"]
		for name, user, national in (("کارمند یک", cls.worker_user, "0012345679"), ("کارمند دو", None, False)):
			employee = cls.env["hr.employee"].create({"name": name, "user_id": user.id if user else False,
				"identification_id": national, "marital": "single"})
			employee.version_id.write({"date_version": "2026-01-01", "contract_date_start": "2026-01-01", "wage": WAGE,
				"struct_id": structure.id, "veron_insurance_number": "1234567" if user else False})
			cls.employees |= employee
		cls.llm = cls.env["veron.ai.provider"].create({"name": "Fake", "kind": "llm", "adapter": "test_fake",
			"is_default": True, "api_key": "k"})
		cls.env["veron.ai.tool"]._sync()
		Tool = cls.env["veron.ai.tool"]
		cls.agent = cls.env["veron.ai.agent"].create({
			"name": "حقوق و دستمزد", "enabled": True, "authority_level": "3", "company_ids": [(6, 0, cls.env.company.ids)],
			"responsible_user_id": cls.manager.id, "llm_provider_id": cls.llm.id,
			"grant_ids": [(0, 0, {"tool_id": Tool._by_codes(code).id, "level": "3"}) for code in TOOLS],
			"scope_ids": [(0, 0, {"model_id": cls.env["ir.model"]._get_id(m)}) for m in ("hr.payslip", "hr.employee")],
		})

	def setUp(self):
		super().setUp()
		FakeAdapter.script, FakeAdapter.calls, FakeAdapter.error = [], [], None

	def start(self, *items, text="حقوق مهر ۱۴۰۵"):
		FakeAdapter.script = [calls(*items), answer("انجام شد")]
		return self.env["veron.ai.run"].with_user(self.manager)._start(self.agent, self.manager, "user", text=text)

	def test_stops_when_rates_are_not_confirmed(self):
		self.assertEqual(self.rates.state, "draft")
		run = self.start(("payroll_inputs_check", {"month": "1405/07"}), ("payslip_drafts_compute", {"month": "1405/07"}))
		self.assertEqual(run.step_ids.mapped("decision"), ["needs_info", "needs_info"])
		self.assertEqual(run.state, "waiting_info")
		self.assertIn("1405", run.approval_ids[0].question)
		self.assertFalse(self.env["hr.payslip"].search([("employee_id", "in", self.employees.ids)]))

	def test_compute_compare_and_pdf(self):
		self.rates.action_confirm()
		run = self.start(("payroll_inputs_check", {"month": "1405/07"}))
		check = json.loads(run.step_ids.output_json)
		self.assertEqual(check["employees"], 2)
		missing = {row["employee"]: row["missing"] for row in check["to_complete"]}
		self.assertIn("no national code", missing["کارمند دو"])
		self.assertIn("no insurance number", missing["کارمند دو"])

		run = self.start(("payslip_drafts_compute", {"month": "1405/06"}), ("payslip_drafts_compute", {"month": "1405/07"}))
		self.assertEqual(run.step_ids.mapped("decision"), ["allowed", "allowed"], run.step_ids.mapped("output_json"))
		payslips = self.env["hr.payslip"].search([("employee_id", "in", self.employees.ids), ("date_from", "=", MEHR[0])])
		self.assertEqual(len(payslips), 2)
		self.assertFalse(payslips.filtered(lambda p: p.state == "done"), "nothing is confirmed or paid")
		self.assertTrue(all(p.line_ids.filtered(lambda l: l.code == "NET") for p in payslips))
		# Salaries are not sent to the language model
		sent = json.dumps([c["messages"] for c in FakeAdapter.calls], ensure_ascii=False, default=str)
		self.assertNotIn(str(WAGE), sent)
		self.assertNotIn(f"{WAGE:,}", sent)

		# A change from last month is shown in percent
		payslip = payslips.filtered(lambda p: p.employee_id.name == "کارمند یک")
		payslip.input_line_ids.filtered(lambda l: l.code == "OVERTIME").amount = 40
		payslip.compute_sheet()
		run = self.start(("payroll_compare_previous", {"month": "1405/07"}))
		compare = json.loads(run.step_ids.output_json)
		self.assertEqual([row["employee"] for row in compare["changes"]], ["کارمند یک"])
		self.assertGreater(compare["changes"][0]["gross_change_percent"], 15)
		self.assertNotIn(str(WAGE), run.step_ids.output_json)

		# The PDFs: each employee's own, and payroll managers
		run = self.start(("payslip_pdf_prepare", {"month": "1405/07", "notify": True}))
		result = json.loads(run.step_ids.output_json)
		self.assertEqual(result["prepared"], 2)
		self.assertEqual(result["employees_told"], 1)
		Document = self.env["veron.payslip.document"]
		mine = Document.with_user(self.worker_user).search([])
		self.assertEqual(mine.employee_id.name, "کارمند یک")
		# In tests Odoo renders reports as HTML instead of PDF; what matters is who may read the file
		self.assertTrue(mine.attachment_id.with_user(self.worker_user).raw)
		self.assertFalse(Document.with_user(self.colleague).search([]))
		with self.assertRaises(AccessError):
			mine.attachment_id.with_user(self.colleague).read(["raw"])
		self.assertEqual(len(Document.with_user(self.manager).search([("month", "=", result["month"])])), 2)

	def test_no_payment_tool(self):
		ours = [t for t in registry.TOOLS.values() if t.module == "veron_ai_agent_payroll"]
		self.assertEqual(len(ours), 4)
		self.assertFalse([t.code for t in ours if t.sensitive or t.level >= 4])
		for tool in ours:
			self.assertNotIn("amount", json.dumps(tool.schema), "an agent gives no amount to payroll")
