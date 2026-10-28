"""Agents of a team once made with one name for all their parts: each is named after its own role again."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
	env = api.Environment(cr, SUPERUSER_ID, {"lang": "fa_IR"})
	Agent = env["veron.ai.agent"].with_context(active_test=False)
	for agent in Agent.search([("template_id", "!=", False)]):
		same = Agent.search([("name", "=", agent.name), ("id", "!=", agent.id), ("template_id", "!=", agent.template_id.id)])
		if same and agent.name != agent.template_id.name:
			agent.name = agent.template_id.name
