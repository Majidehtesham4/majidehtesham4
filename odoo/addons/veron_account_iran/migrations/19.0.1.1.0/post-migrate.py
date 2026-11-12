from odoo import SUPERUSER_ID, api


def migrate(cr, version):
	"""The ways of paying named in English when the chart was installed: named in the company's language"""
	env = api.Environment(cr, SUPERUSER_ID, {})
	env["account.payment.method.line"]._veron_rename()
