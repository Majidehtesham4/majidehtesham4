from odoo import api, fields, models


class ResUsersSettings(models.Model):
	_inherit = "res.users.settings"

	# Dark unless the person chooses light
	dark_mode = fields.Boolean(default=True)


class ResUsers(models.Model):
	_inherit = "res.users"

	@api.depends("action_id")
	def _compute_redirect_home(self):
		# The home screen of the apps first, unless the user has a home action of their own
		for user in self:
			user.is_redirect_home = not user.action_id

	@api.model_create_multi
	def create(self, vals_list):
		users = super().create(vals_list)
		Settings = self.env["res.users.settings"].sudo()
		for user in users.filtered(lambda u: not u.share):
			Settings._find_or_create_for_user(user)
		return users
