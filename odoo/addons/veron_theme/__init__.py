from . import models


def post_init_hook(env):
	"""The people already there start in the dark theme, on the home screen of the apps; their later choice is theirs"""
	users = env["res.users"].with_context(active_test=False).search([("share", "=", False)])
	Settings = env["res.users.settings"].sudo()
	for user in users:
		Settings._find_or_create_for_user(user).dark_mode = True
	users.filtered(lambda u: not u.action_id).write({"is_redirect_home": True})
