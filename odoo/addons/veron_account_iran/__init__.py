from . import models
from . import wizard


def post_init_hook(env):
	"""The deposit taxes for the companies already on the Iranian chart"""
	for company in env["res.company"].search([]):
		env["account.tax"]._veron_retentions(company)
