from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLetters(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.clerk = new_test_user(cls.env, "veron_clerk", groups="base.group_user,veron_secretariat.group_user")
		cls.other = new_test_user(cls.env, "veron_other", groups="base.group_user")
		cls.boss = new_test_user(cls.env, "veron_boss", groups="base.group_user")
		cls.sender = cls.env["res.partner"].create({"name": "اداره دارایی"})

	def letter(self, **values):
		values.setdefault("subject", "درخواست مدارک")
		return self.env["veron.letter"].with_user(self.clerk).create(values)

	def test_numbers_by_series_and_year(self):
		incoming = self.letter(kind="incoming", partner_id=self.sender.id, date="2026-10-01", their_number="45/12")
		outgoing = self.letter(kind="outgoing", date="2026-10-02")
		second = self.letter(kind="outgoing", date="2026-10-03")
		(incoming | outgoing | second).action_register()
		self.assertEqual(incoming.name.split("/")[1:], ["و", str(incoming.sequence_number)])
		self.assertEqual(second.sequence_number, outgoing.sequence_number + 1)
		self.assertTrue(outgoing.name.startswith("1405/ص/"))
		with self.assertRaises(UserError):
			outgoing.name = "1405/ص/999"
		with self.assertRaises(UserError):
			outgoing.unlink()
		with self.assertRaises(UserError):
			self.letter(kind="incoming").action_register()

	def test_confidential_seen_by_those_it_concerns(self):
		secret = self.letter(kind="internal", classification="secret", user_ids=[(6, 0, self.boss.ids)])
		ordinary = self.letter(kind="internal")
		Letter = self.env["veron.letter"]
		self.assertIn(ordinary, Letter.with_user(self.other).search([]))
		self.assertNotIn(secret, Letter.with_user(self.other).search([]))
		with self.assertRaises(AccessError):
			secret.with_user(self.other).read(["subject"])
		self.assertEqual(secret.with_user(self.boss).subject, "درخواست مدارک")
		secret.with_user(self.clerk).referral_ids = [(0, 0, {"user_id": self.other.id, "instruction": "جهت اقدام"})]
		self.assertIn(secret, Letter.with_user(self.other).search([]), "referred to them, they see it")

	def test_referral_is_a_todo(self):
		letter = self.letter(kind="incoming", partner_id=self.sender.id)
		letter.action_register()
		letter.referral_ids = [(0, 0, {"user_id": self.boss.id, "instruction": "جهت پاسخ", "deadline": "2026-11-20"})]
		referral = letter.referral_ids
		self.assertEqual((referral.activity_id.user_id, str(referral.activity_id.date_deadline)), (self.boss, "2026-11-20"))
		with self.assertRaises(UserError):
			referral.with_user(self.other).sudo(False).action_done()
		referral.answer = "پاسخ داده شد"
		referral.with_user(self.boss).action_done()
		self.assertEqual(referral.state, "done")
		activity = referral.activity_id.with_context(active_test=False)
		self.assertFalse(activity.exists() and activity.active, "the to-do is done")
		html = self.env["ir.actions.report"]._render_qweb_html("veron_secretariat.report_letter", letter.ids)[0].decode()
		self.assertIn(letter.name, html)

	def test_administrator_registers_letters(self):
		"""the administrator manages the secretariat from the start, as in the other apps"""
		admin = self.env.ref("base.user_admin")
		self.assertTrue(admin.has_group("veron_secretariat.group_manager"))
