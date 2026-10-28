"""A supervisor and its team made by the wizard: the parts are linked to it, nothing is made twice, and the
built-in assistant of the supervisor gives a task to the part that has its tool"""

from odoo.tests import tagged

from .common import AgentCase


@tagged("post_install", "-at_install")
class TestTeamWizard(AgentCase):
	def test_team_made_and_used(self):
		self.env["veron.ai.agent"].search([]).write({"enabled": False})
		Wizard = self.env["veron.ai.team.wizard"].with_user(self.manager)
		receivables = self.env.ref("veron_ai_agent.role_fin_receivables")
		wizard = Wizard.create({"understood": True})
		self.assertEqual(wizard.supervisor_template_id, self.env.ref("veron_ai_agent.role_sup_finance"))
		wizard.write({"name": "تیم آزمایشی", "member_template_ids": [(6, 0, receivables.ids)]})
		self.assertIn(receivables.name, wizard.explanation)
		supervisor = self.env["veron.ai.agent"].browse(wizard.action_create()["res_id"])
		self.assertEqual(supervisor.delegate_agent_ids.template_id, receivables)
		self.assertTrue(supervisor.enabled and supervisor.delegate_agent_ids.enabled)
		self.assertEqual(supervisor.delegate_agent_ids.supervisor_agent_id, supervisor)
		before = self.env["veron.ai.agent"].search_count([])
		Wizard.create({"understood": True, "name": "تیم آزمایشی", "member_template_ids": [(6, 0, receivables.ids)]}
			).action_create()
		self.assertEqual(self.env["veron.ai.agent"].search_count([]), before, "nothing is made twice")
		# The supervisor has no tool of its own: the part with the tool does the task
		supervisor.write({"engine": "internal"}) if "engine" in supervisor._fields else None
		Chat = self.env["veron.ai.conversation"].with_user(self.manager)
		conversation = Chat.veron_chat_open(supervisor.id)["conversation_id"]
		reply = Chat.veron_chat_send(conversation, "مطالبات سررسید گذشته", [], {}, "internal")[-1]
		self.assertIn(receivables.name, reply["body_html"], reply["body_html"])
