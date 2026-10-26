from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAppraisal(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		Users = cls.env["res.users"].with_context(no_reset_password=True)
		internal = cls.env.ref("base.group_user")
		cls.boss_user = Users.create({"name": "مدیر", "login": "boss_appr", "group_ids": [(6, 0, internal.ids)]})
		cls.emp_user = Users.create({"name": "کارمند", "login": "emp_appr", "group_ids": [(6, 0, internal.ids)]})
		cls.other_user = Users.create({"name": "دیگری", "login": "other_appr", "group_ids": [(6, 0, internal.ids)]})
		Emp = cls.env["hr.employee"]
		cls.boss = Emp.create({"name": "مدیر", "user_id": cls.boss_user.id})
		cls.emp = Emp.create({"name": "کارمند", "user_id": cls.emp_user.id, "parent_id": cls.boss.id})
		cls.other = Emp.create({"name": "دیگری", "user_id": cls.other_user.id})
		cls.appraisal = cls.emp.action_veron_start_appraisals() and cls.env["veron.appraisal"].search([("employee_id", "=", cls.emp.id)])

	def test_started(self):
		a = self.appraisal
		self.assertEqual(a.state, "pending")
		self.assertEqual(a.manager_id, self.boss)
		self.assertEqual(len(a.line_ids), 8)
		self.assertEqual(set(a.activity_ids.mapped("user_id").ids), {self.emp_user.id, self.boss_user.id})

	def test_who_writes_what(self):
		lines = self.appraisal.line_ids.filtered(lambda l: l.kind == "rating")
		lines[0].with_user(self.emp_user).employee_rating = "4"
		with self.assertRaises(AccessError):
			lines[0].with_user(self.emp_user).manager_rating = "5"
		with self.assertRaises(AccessError):
			lines[0].with_user(self.boss_user).employee_rating = "1"
		with self.assertRaises(AccessError):
			lines[0].with_user(self.emp_user).name = "سؤال دیگر"
		with self.assertRaises(AccessError):
			self.appraisal.with_user(self.emp_user).manager_feedback = "<p>خوب</p>"
		with self.assertRaises(AccessError):
			self.appraisal.with_user(self.boss_user).date_to = "2020-01-01"
		# Someone else sees nothing of it
		self.assertFalse(self.env["veron.appraisal"].with_user(self.other_user).search([("id", "=", self.appraisal.id)]))

	def test_score_and_close(self):
		a = self.appraisal
		with self.assertRaises(UserError):
			a.with_user(self.boss_user).action_done()  # not every question rated
		ratings = {"Quality of work": "5", "Productivity and meeting deadlines": "3"}
		for line in a.line_ids.filtered(lambda l: l.kind == "rating"):
			line.with_user(self.boss_user).manager_rating = ratings.get(line.with_context(lang="en_US").name, "4")
		# (5*2 + 3*2 + 4*4) / 8 = 4.0
		self.assertAlmostEqual(a.score, 4.0)
		self.assertEqual(a.result, "4")
		with self.assertRaises(AccessError):
			a.with_user(self.emp_user).action_done()
		a.with_user(self.boss_user).action_done()
		self.assertEqual(a.state, "done")
		self.assertFalse(a.activity_ids)
		with self.assertRaises(UserError):
			a.line_ids[0].with_user(self.emp_user).employee_rating = "2"
		self.assertEqual(self.emp.veron_last_appraisal, a.date_to)
