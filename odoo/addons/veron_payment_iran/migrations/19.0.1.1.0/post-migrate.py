"""The gateways of the banks added: each given its payment method, as a new installation does"""

from odoo import api

from odoo.addons.payment import setup_provider


def migrate(cr, version):
	env = api.Environment(cr, 1, {})
	for code in ("mellat", "sadad", "asanpardakht"):
		setup_provider(env, code)
