from . import controllers
from . import models

from odoo.addons.payment import reset_payment_provider, setup_provider

CODES = ("zarinpal", "zibal")


def post_init_hook(env):
	for code in CODES:
		setup_provider(env, code)


def uninstall_hook(env):
	for code in CODES:
		reset_payment_provider(env, code)
