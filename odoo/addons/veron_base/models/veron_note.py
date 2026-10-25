from odoo import api, fields, models


class VeronNote(models.Model):
	"""A short note: the smallest model there is, to see how Odoo modules are made."""

	_name = "veron.note"
	_description = "یادداشت"
	_order = "date desc, id desc"

	name = fields.Char("عنوان", required=True)
	date = fields.Date("تاریخ", default=fields.Date.context_today)
	partner_id = fields.Many2one("res.partner", "طرف حساب")
	amount = fields.Float("مبلغ")
	state = fields.Selection([("open", "باز"), ("done", "انجام شد")], "وضعیت", default="open")
	body = fields.Text("متن")
	words = fields.Integer("تعداد کلمه", compute="_compute_words", store=True)

	@api.depends("body")
	def _compute_words(self):
		for note in self:
			note.words = len((note.body or "").split())

	def action_done(self):
		self.state = "done"
