from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestShopfloor(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env.user.group_ids |= cls.env.ref("mrp.group_mrp_routings")
		cls.api = cls.env["veron.shopfloor"]
		cls.cutting = cls.env["mrp.workcenter"].create({"name": "برش"})
		cls.assembly = cls.env["mrp.workcenter"].create({"name": "مونتاژ"})
		cls.table = cls.env["product.product"].create({"name": "میز", "is_storable": True})
		cls.wood = cls.env["product.product"].create({"name": "چوب", "is_storable": True})
		bom = cls.env["mrp.bom"].create({
			"product_tmpl_id": cls.table.product_tmpl_id.id, "product_qty": 1,
			"bom_line_ids": [(0, 0, {"product_id": cls.wood.id, "product_qty": 4})],
			"operation_ids": [
				(0, 0, {"name": "برش چوب", "workcenter_id": cls.cutting.id, "time_cycle_manual": 30}),
				(0, 0, {"name": "مونتاژ میز", "workcenter_id": cls.assembly.id, "time_cycle_manual": 60}),
			],
		})
		cls.production = cls.env["mrp.production"].create({"product_id": cls.table.id, "product_qty": 2, "bom_id": bom.id})
		cls.production.action_confirm()

	def test_flow(self):
		centers = {c["name"]: c for c in self.api.workcenters()}
		self.assertIn("برش", centers)
		cut = self.api.workorders(self.cutting.id)
		self.assertEqual(len(cut), 1)
		self.assertEqual(cut[0]["quantity"], 2)
		self.assertEqual(cut[0]["components"][0]["quantity"], 8)
		wo = self.env["mrp.workorder"].browse(cut[0]["id"])

		data = self.api.act(wo.id, "start")["workorders"][0]
		self.assertTrue(data["working"])
		self.assertTrue(data["running_since"])
		self.assertEqual(wo.state, "progress")
		self.api.act(wo.id, "pause")
		self.assertFalse(wo.is_user_working)
		result = self.api.act(wo.id, "done", 2)
		self.assertEqual(wo.state, "done")
		self.assertFalse(result["finish"])  # assembly still to do

		assembly = self.production.workorder_ids - wo
		result = self.api.act(assembly.id, "done", 2)
		self.assertEqual(result["finish"]["id"], self.production.id)
		finished = self.api.finish_production(self.production.id)
		if "action" in finished:
			# Odoo asks first (components not reserved: consumed anyway?), as on its own form
			self.assertTrue(finished["action"].get("res_model"))
		else:
			self.assertEqual(self.production.state, "done")

	def test_scrap_action(self):
		wo = self.production.workorder_ids[:1]
		action = self.api.scrap(wo.id)
		self.assertEqual(action["res_model"], "stock.scrap")
