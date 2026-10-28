"""The guides of the AI sections: each opens from its section's pages, and the lists in them come from the program's
data and the person's own rights"""

from odoo.tests import tagged

from .common import AgentCase


@tagged("post_install", "-at_install")
class TestGuides(AgentCase):
	def test_every_guide_opens(self):
		Guide = self.env["veron.ai.guide"].with_user(self.user)
		codes = set(Guide.search([]).mapped("code"))
		self.assertTrue({"start", "assistant", "talk", "library", "agents", "roles", "team", "approvals", "runs", "tools",
			"connect"} <= codes)
		for guide in Guide.search([]):
			self.assertTrue(guide.body, guide.code)
			if guide.action_ref:
				self.assertTrue(guide.action_open_section()["type"].startswith("ir.actions"), guide.code)

	def test_buttons_of_the_sections(self):
		action = self.env["veron.ai.agent"].with_user(self.manager).with_context(guide="team").action_veron_guide()
		self.assertEqual(self.env["veron.ai.guide"].browse(action["res_id"]).code, "team")
		action = self.env["veron.ai.guide"].with_user(self.user).action_by_code("no such section")
		self.assertEqual(self.env["veron.ai.guide"].browse(action["res_id"]).code, "start")

	def test_lists_from_the_data(self):
		library = self.env["veron.ai.guide"].with_user(self.user).search([("code", "=", "library")])
		intent = self.env["veron.ai.intent"].search([("code", "=", "contact_find")])
		self.assertIn(intent.name, library.details)
		tools = self.env["veron.ai.guide"].with_user(self.manager).search([("code", "=", "tools")])
		self.assertIn("<table", tools.details)
