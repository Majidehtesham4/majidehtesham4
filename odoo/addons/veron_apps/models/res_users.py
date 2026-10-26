from odoo import api, models


class ResUsers(models.Model):
	_inherit = "res.users"

	@api.depends("action_id")
	def _compute_redirect_home(self):
		"""Signing in opens the apps menu (web_responsive's «Redirect to Home»), not the first app of the
		menu, unless the user was given a home action of their own. web_responsive leaves it off."""
		for user in self:
			user.is_redirect_home = not user.action_id

	@api.model
	def _veron_redirect_home(self):
		"""The users there already, when the module is installed or updated."""
		self.with_context(active_test=False).search([("action_id", "=", False)]).is_redirect_home = True
