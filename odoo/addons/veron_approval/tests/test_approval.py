from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestApproval(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		Users = cls.env["res.users"].with_context(no_reset_password=True)
		internal = cls.env.ref("base.group_user")
		cls.clerk = Users.create({"name": "کارمند", "login": "clerk_appr", "group_ids": [(6, 0, internal.ids)]})
		cls.boss1 = Users.create({"name": "مدیر یک", "login": "boss1_appr", "group_ids": [(6, 0, internal.ids)]})
		cls.boss2 = Users.create({"name": "مدیر دو", "login": "boss2_appr", "group_ids": [(6, 0, internal.ids)]})
		cls.other = Users.create({"name": "دیگری", "login": "other_appr", "group_ids": [(6, 0, internal.ids)]})
		cls.category = cls.env["veron.approval.category"].create({
			"name": "خرید", "has_amount": "required", "minimum": 2, "approver_ids": [(6, 0, (cls.boss1 | cls.boss2).ids)]})

	def request(self):
		return self.env["veron.approval.request"].with_user(self.clerk).create({"name": "خرید لپ‌تاپ", "category_id": self.category.id})

	def test_two_approvals_needed(self):
		req = self.request()
		self.assertTrue(req.reference.startswith("APR/"))
		with self.assertRaises(UserError):
			req.action_submit()  # amount required
		req.amount = 450000000
		req.action_submit()
		self.assertEqual(req.state, "pending")
		self.assertEqual(set(req.activity_ids.mapped("user_id").ids), {self.boss1.id, self.boss2.id})
		with self.assertRaises(AccessError):
			req.with_user(self.clerk).action_approve()
		with self.assertRaises(AccessError):
			req.with_user(self.clerk).write({"amount": 1})  # not while pending
		req.with_user(self.boss1).action_approve()
		self.assertEqual(req.state, "pending")
		req.with_user(self.boss2).action_approve()
		self.assertEqual(req.state, "approved")
		self.assertFalse(req.activity_ids)

	def test_refuse_and_visibility(self):
		req = self.request()
		req.amount = 1000
		req.action_submit()
		self.assertFalse(self.env["veron.approval.request"].with_user(self.other).search([("id", "=", req.id)]))
		self.assertTrue(self.env["veron.approval.request"].with_user(self.boss1).search([("id", "=", req.id)]))
		self.env["veron.approval.refuse"].with_user(self.boss1).create({"request_id": req.id, "reason": "بودجه نیست"}).action_refuse()
		self.assertEqual(req.state, "refused")
		self.assertEqual(req.approver_line_ids.filtered(lambda l: l.user_id == self.boss1).comment, "بودجه نیست")
		with self.assertRaises(AccessError):
			req.with_user(self.boss2).action_approve()
