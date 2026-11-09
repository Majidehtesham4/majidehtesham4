from odoo import _, fields, models
from odoo.exceptions import UserError


class RotationGenerate(models.TransientModel):
	_name = "veron.planning.rotation.generate"
	_description = "Make the Shifts of Rotating Patterns"

	rotation_ids = fields.Many2many("veron.planning.rotation", string="Patterns", required=True,
		default=lambda self: self.env.context.get("active_model") == "veron.planning.rotation"
		and self.env.context.get("active_ids"))
	date_from = fields.Date(required=True, default=fields.Date.context_today)
	date_to = fields.Date(required=True)
	result = fields.Text(readonly=True)

	def action_generate(self):
		self.ensure_one()
		if self.date_to < self.date_from:
			raise UserError(_("The period ends before it starts."))
		if (self.date_to - self.date_from).days > 92:
			raise UserError(_("Shifts are made for three months at most at once."))
		Shift = self.env["veron.planning.shift"]
		made, skipped = Shift, 0
		for rotation in self.rotation_ids:
			for values in rotation._shifts(self.date_from, self.date_to):
				# Never over a shift the person already has, drafts made before included
				if Shift.search_count([("employee_id", "=", values["employee_id"]),
						("start_datetime", "<", values["end_datetime"]), ("end_datetime", ">", values["start_datetime"])]):
					skipped += 1
					continue
				made |= Shift.create(values)
		self.result = _("%(made)s draft shifts made; %(skipped)s not made, as the person already has a shift then. "
			"Check them and publish them in the planning.", made=len(made), skipped=skipped)
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
			"target": "new"}
