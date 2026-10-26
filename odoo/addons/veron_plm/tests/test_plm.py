from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlm(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		P = cls.env["product.product"]
		cls.chair = P.create({"name": "صندلی", "is_storable": True})
		cls.wood = P.create({"name": "پایه چوبی", "is_storable": True})
		cls.steel = P.create({"name": "پایه فلزی", "is_storable": True})
		cls.screw = P.create({"name": "پیچ", "is_storable": True})
		cls.bom = cls.env["mrp.bom"].create({
			"product_tmpl_id": cls.chair.product_tmpl_id.id,
			"bom_line_ids": [(0, 0, {"product_id": cls.wood.id, "product_qty": 4}), (0, 0, {"product_id": cls.screw.id, "product_qty": 8})],
		})
		cls.engineer = cls.env["res.users"].create({
			"name": "مهندس", "login": "engineer_plm",
			"group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("veron_plm.group_plm_engineer").id])],
		})

	def test_change_cycle(self):
		eco = self.env["veron.plm.eco"].with_user(self.engineer).create({
			"title": "پایه فلزی به جای چوبی", "product_tmpl_id": self.chair.product_tmpl_id.id, "bom_id": self.bom.id})
		self.assertTrue(eco.name.startswith("ECO/"))
		eco.action_start()
		new = eco.new_bom_id
		self.assertFalse(new.active)
		self.assertEqual(new.veron_version, 2)
		self.assertEqual(new.veron_previous_bom_id, self.bom)
		# Production still finds the current version only
		self.assertEqual(self.env["mrp.bom"]._bom_find(self.chair)[self.chair], self.bom)
		with self.assertRaises(UserError):
			eco.action_request_approval()  # nothing changed yet
		# The engineer changes the draft version, never the version in use
		new = new.with_user(self.engineer)
		new.bom_line_ids.filtered(lambda l: l.product_id == self.wood).product_id = self.steel
		new.bom_line_ids.filtered(lambda l: l.product_id == self.screw).product_qty = 12
		with self.assertRaises(AccessError):
			self.bom.with_user(self.engineer).bom_line_ids[:1].product_qty = 99
		kinds = sorted(r[1] for r in eco._diff())
		self.assertEqual(len(kinds), 3)  # wood removed, steel added, screws 8 -> 12
		self.assertIn("12", str(eco.changes))
		eco.action_request_approval()
		with self.assertRaises(AccessError):
			eco.action_approve()  # an engineer does not approve
		eco.with_user(self.env.ref("base.user_admin")).action_approve()
		eco.action_apply()
		self.assertEqual(eco.state, "done")
		self.assertTrue(new.active)
		self.assertFalse(self.bom.active)
		self.assertEqual(self.env["mrp.bom"]._bom_find(self.chair)[self.chair], new)

	def test_cancel_removes_the_draft_version(self):
		eco = self.env["veron.plm.eco"].create({"title": "x", "product_tmpl_id": self.chair.product_tmpl_id.id, "bom_id": self.bom.id})
		eco.action_start()
		new = eco.new_bom_id
		eco.action_cancel()
		self.assertFalse(new.exists())
		self.assertTrue(self.bom.active)
