"""One-time codes sent by SMS to log in with a mobile number, and the one-time token that logs the person in
once the code is right. Only their hashes are kept."""

import datetime
import hashlib
import hmac
import re
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError

LIFETIME = datetime.timedelta(minutes=2)
TRIES = 5
# At most one code a minute for a number, and ten an hour from an address
NUMBER_WAIT = datetime.timedelta(minutes=1)
ADDRESS_LIMIT = 10


def mobile(number):
	"""09121234567 of an Iranian mobile number written in any way; None when it is not one"""
	digits = (number or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
	digits = re.sub(r"[^\d+]", "", digits)
	for prefix in ("+98", "0098", "98"):
		if digits.startswith(prefix) and len(digits) - len(prefix) == 10:
			digits = "0" + digits[len(prefix):]
	if len(digits) == 10 and digits.startswith("9"):
		digits = "0" + digits
	return digits if re.fullmatch(r"09\d{9}", digits) else None


class LoginCode(models.Model):
	_name = "veron.login.code"
	_description = "Login Code by SMS"
	_order = "id desc"

	mobile = fields.Char(required=True, index=True)
	code_hash = fields.Char(required=True)
	token_hash = fields.Char()
	user_id = fields.Many2one("res.users", ondelete="cascade")
	expires = fields.Datetime(required=True)
	tries = fields.Integer(default=0)
	used = fields.Boolean()
	address = fields.Char(index=True)

	@api.model
	def _hash(self, value):
		secret = self.env["ir.config_parameter"].sudo().get_param("database.secret") or ""
		return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()

	@api.model
	def _send(self, number, address):
		"""A new code for the number, sent by SMS; refused when the number or the address asks too often"""
		number = mobile(number)
		if not number:
			raise UserError(_("This is not a mobile number."))
		now = fields.Datetime.now()
		if self.search_count([("mobile", "=", number), ("create_date", ">", now - NUMBER_WAIT)]):
			raise UserError(_("A code was just sent to this number; wait a minute."))
		if address and self.search_count([("address", "=", address), ("create_date", ">", now - datetime.timedelta(hours=1))]) \
				>= ADDRESS_LIMIT:
			raise UserError(_("Too many codes were asked from here; try again later."))
		code = f"{secrets.randbelow(1_000_000):06d}"
		self.search([("mobile", "=", number), ("used", "=", False)]).write({"used": True})
		self.create({"mobile": number, "code_hash": self._hash(f"{number}:{code}"), "expires": now + LIFETIME,
			"address": address})
		self.env["sms.sms"].sudo().create({"number": number,
			"body": _("Your login code: %(code)s\n%(site)s", code=code, site=self.env.company.name)})._send()
		return number

	@api.model
	def _check(self, number, code):
		"""The user of a right code (made a portal user when the number is new and sign-up is open), and a token to
		log them in once; a wrong code counts a try"""
		number = mobile(number)
		record = self.search([("mobile", "=", number), ("used", "=", False)], limit=1) if number else self.browse()
		if not record or record.expires < fields.Datetime.now() or record.tries >= TRIES:
			raise AccessDenied(_("The code has expired; ask for a new one."))
		if not hmac.compare_digest(record.code_hash, self._hash(f"{number}:{(code or '').strip()}")):
			record.tries += 1
			raise AccessDenied(_("The code is not right."))
		user = self._user(number)
		token = secrets.token_urlsafe(32)
		record.write({"used": True, "user_id": user.id, "token_hash": self._hash(token)})
		return user, token

	@api.model
	def _user(self, number):
		Users = self.env["res.users"].sudo().with_context(active_test=False)
		forms = {number, "+98" + number[1:], "98" + number[1:]}
		users = Users.search([("login", "in", list(forms))]) or Users.search([("partner_id.phone", "in", list(forms))])
		users = users.filtered("active")
		website = self.env["website"].get_current_website()
		if len(users) > 1:
			raise AccessDenied(_("More than one account has this number; log in with your password."))
		if users:
			if not users._is_portal() and not website.veron_otp_internal:
				raise AccessDenied(_("Log in to this account with its password."))
			return users
		if self.env["res.users"].sudo()._get_signup_invitation_scope() != "b2c":
			raise AccessDenied(_("No account has this number, and sign-up is closed."))
		user = self.env["res.users"].sudo().with_context(no_reset_password=True)._signup_create_user({
			"login": number, "name": number, "phone": number})
		if "res.users.settings" in self.env:
			# Made now, not by the first page the new user opens (which only reads)
			self.env["res.users.settings"].sudo()._find_or_create_for_user(user)
		return user


class ResUsers(models.Model):
	_inherit = "res.users"

	def _check_credentials(self, credential, env):
		if credential.get("type") != "veron_otp":
			return super()._check_credentials(credential, env)
		Code = self.env["veron.login.code"].sudo()
		record = Code.search([("user_id", "=", self.env.user.id), ("token_hash", "=", Code._hash(credential.get("token") or ""))],
			limit=1)
		if not record or record.expires + LIFETIME < fields.Datetime.now():
			raise AccessDenied()
		# Once: the token cannot log in again
		record.token_hash = False
		return {"uid": self.env.user.id, "auth_method": "veron_otp", "mfa": "default"}
