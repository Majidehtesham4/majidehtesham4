from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.veron_core.models import jalali

KINDS = [("incoming", "Incoming"), ("outgoing", "Outgoing"), ("internal", "Internal")]
# The letter of each series in its number: «و» وارده، «ص» صادره، «د» داخلی
PREFIX = {"incoming": "و", "outgoing": "ص", "internal": "د"}


def shamsi(value):
	if not value:
		return ""
	year, month, day = jalali.to_jalali(fields.Date.to_date(value))
	return f"{year}/{month:02d}/{day:02d}"


class Letter(models.Model):
	_name = "veron.letter"
	_description = "Letter"
	_inherit = ["mail.thread", "mail.activity.mixin"]
	_order = "date desc, id desc"

	name = fields.Char("Number", readonly=True, copy=False, default="/", tracking=True)
	sequence_year = fields.Integer(readonly=True, copy=False)
	sequence_number = fields.Integer(readonly=True, copy=False)
	kind = fields.Selection(KINDS, required=True, default="outgoing", tracking=True)
	date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
	subject = fields.Char(required=True, tracking=True)
	partner_id = fields.Many2one("res.partner", "Organization or Person", tracking=True,
		help="Who sent an incoming letter, or who an outgoing one is to")
	user_ids = fields.Many2many("res.users", "veron_letter_user_rel", "letter_id", "user_id", "To",
		help="The people of the organization it is for")
	signer_id = fields.Many2one("res.users", "Signed By", tracking=True)
	their_number = fields.Char("Their Number", help="The number the sender gave an incoming letter")
	their_date = fields.Date("Their Date")
	priority = fields.Selection([("0", "Normal"), ("1", "Urgent"), ("2", "Immediate")], default="0", tracking=True)
	classification = fields.Selection([("normal", "Normal"), ("confidential", "Confidential"), ("secret", "Secret")],
		default="normal", required=True, tracking=True)
	body = fields.Html()
	enclosure = fields.Char("Enclosures", help="What is sent with it, as «دو برگ»; empty for none")
	state = fields.Selection([("draft", "Draft"), ("registered", "Registered"), ("archived", "Archived")], default="draft",
		required=True, tracking=True, copy=False)
	follows_id = fields.Many2one("veron.letter", "Following Up", help="پیرو")
	reference_id = fields.Many2one("veron.letter", "In Reference To", help="عطف")
	answers_id = fields.Many2one("veron.letter", "In Answer To", help="بازگشت")
	referral_ids = fields.One2many("veron.letter.referral", "letter_id", "Referrals")
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

	def _shamsi(self, value):
		return shamsi(value)

	def action_register(self):
		"""The number of the next letter of its series in the Shamsi year of its date"""
		for letter in self.filtered(lambda l: l.state == "draft").sorted(lambda l: (l.date, l.id)):
			if letter.kind == "incoming" and not letter.partner_id:
				raise UserError(_("Say who sent the incoming letter."))
			year = jalali.to_jalali(letter.date)[0]
			self.flush_model(["sequence_number", "sequence_year"])
			self.env.cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", [7_310_406, letter.company_id.id * 10_000 + year])
			self.env.cr.execute("SELECT COALESCE(MAX(sequence_number), 0) FROM veron_letter WHERE company_id = %s AND "
				"kind = %s AND sequence_year = %s", [letter.company_id.id, letter.kind, year])
			number = self.env.cr.fetchone()[0] + 1
			letter.write({"sequence_year": year, "sequence_number": number, "state": "registered",
				"name": f"{year}/{PREFIX[letter.kind]}/{number}"})

	def action_archive_letter(self):
		self.filtered(lambda l: l.state == "registered").write({"state": "archived"})

	def write(self, vals):
		if "name" in vals and not self.env.context.get("veron_letter_number"):
			for letter in self:
				if letter.state != "draft" and vals["name"] != letter.name and "sequence_number" not in vals:
					raise UserError(_("The number of a registered letter is not changed."))
		return super().write(vals)

	def unlink(self):
		if any(letter.state != "draft" for letter in self):
			raise UserError(_("A registered letter is not deleted; it is archived."))
		return super().unlink()


class LetterReferral(models.Model):
	"""A letter given to a person to act on, with what to do and by when; it is a to-do of theirs"""

	_name = "veron.letter.referral"
	_description = "Referral of a Letter"
	_order = "create_date desc, id desc"

	letter_id = fields.Many2one("veron.letter", required=True, ondelete="cascade")
	from_id = fields.Many2one("res.users", "From", default=lambda self: self.env.user, readonly=True)
	user_id = fields.Many2one("res.users", "To", required=True)
	instruction = fields.Char(required=True, help="What to do: «جهت اقدام»، «جهت استحضار»، «جهت پاسخ»")
	deadline = fields.Date()
	state = fields.Selection([("pending", "Pending"), ("done", "Done")], default="pending", required=True)
	answer = fields.Text()
	activity_id = fields.Many2one("mail.activity", readonly=True)

	@api.model_create_multi
	def create(self, vals_list):
		referrals = super().create(vals_list)
		for referral in referrals:
			activity = referral.letter_id.sudo().activity_schedule("mail.mail_activity_data_todo",
				date_deadline=referral.deadline or fields.Date.context_today(referral), user_id=referral.user_id.id,
				summary=referral.instruction, note=referral.letter_id.subject)
			referral.activity_id = activity
			referral.letter_id.message_post(body=_("Referred to %(user)s: %(what)s", user=referral.user_id.name,
				what=referral.instruction))
		return referrals

	def action_done(self):
		for referral in self.filtered(lambda r: r.state == "pending"):
			if referral.user_id != self.env.user and not self.env.user.has_group("veron_secretariat.group_manager"):
				raise UserError(_("Only the person it is referred to marks it done."))
			referral.state = "done"
			if referral.activity_id.exists():
				referral.activity_id.sudo().action_feedback(feedback=referral.answer or "")
			referral.letter_id.message_post(body=_("%(user)s: done. %(answer)s", user=referral.user_id.name,
				answer=referral.answer or ""))
