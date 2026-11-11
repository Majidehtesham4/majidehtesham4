"""Skills, knowledge and triggers: the skills of the program are made; the tools already granted stay as they were"""


def migrate(cr, version):
	from odoo import SUPERUSER_ID, api

	env = api.Environment(cr, SUPERUSER_ID, {})
	env["veron.ai.skill"]._setup_builtin()
