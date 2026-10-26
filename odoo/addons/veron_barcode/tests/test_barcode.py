from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBarcode(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.api = cls.env["veron.barcode"]
		cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
		cls.stock = cls.warehouse.lot_stock_id
		cls.tea = cls.env["product.product"].create({"name": "چای", "is_storable": True, "barcode": "6260001000011"})
		cls.rice = cls.env["product.product"].create({"name": "برنج", "is_storable": True, "barcode": "6260001000028"})
		cls.other = cls.env["product.product"].create({"name": "قند", "is_storable": True, "barcode": "6260001000035"})
		if "product.uom" in cls.env:
			dozen = cls.env.ref("uom.product_uom_dozen")
			cls.env["product.uom"].create({"product_id": cls.tea.id, "uom_id": dozen.id, "barcode": "BOX-TEA-12"})
		cls.receipt = cls.env["stock.picking"].create({
			"picking_type_id": cls.warehouse.in_type_id.id,
			"location_id": cls.env.ref("stock.stock_location_suppliers").id,
			"location_dest_id": cls.stock.id,
			"move_ids": [
				(0, 0, {"product_id": cls.tea.id, "product_uom_qty": 15, "product_uom": cls.tea.uom_id.id,
						"location_id": cls.env.ref("stock.stock_location_suppliers").id, "location_dest_id": cls.stock.id}),
				(0, 0, {"product_id": cls.rice.id, "product_uom_qty": 2, "product_uom": cls.rice.uom_id.id,
						"location_id": cls.env.ref("stock.stock_location_suppliers").id, "location_dest_id": cls.stock.id}),
			],
		})
		cls.receipt.action_confirm()

	def line(self, data, product):
		return next(l for l in data["lines"] if l["product"] == product.display_name)

	def test_receive_by_scanning(self):
		self.assertEqual(self.api.scan(self.receipt.name), {"type": "picking", "id": self.receipt.id})
		data = self.api.picking_scan(self.receipt.id, "6260001000011")
		self.assertEqual(self.line(data, self.tea)["quantity"], 1)
		self.assertEqual(data["level"], "success")
		if "product.uom" in self.env:
			data = self.api.picking_scan(self.receipt.id, "BOX-TEA-12")
			self.assertEqual(self.line(data, self.tea)["quantity"], 13)
		data = self.api.picking_scan(self.receipt.id, "6260001000035")
		self.assertEqual(data["level"], "danger")  # not in this receipt
		data = self.api.picking_scan(self.receipt.id, "nothing-like-this")
		self.assertEqual(data["level"], "danger")
		self.api.picking_set(self.receipt.move_ids.filtered(lambda m: m.product_id == self.tea).id, 15)
		self.api.picking_set(self.receipt.move_ids.filtered(lambda m: m.product_id == self.rice).id, 2)
		result = self.api.picking_validate(self.receipt.id)
		self.assertEqual(self.receipt.state, "done", result)
		self.assertEqual(self.tea.with_context(location=self.stock.id).qty_available, 15)

	def test_validate_with_nothing_scanned(self):
		result = self.api.picking_validate(self.receipt.id)
		self.assertEqual(result["data"]["level"], "danger")
		self.assertNotEqual(self.receipt.state, "done")

	def test_partial_receipt_asks_for_backorder(self):
		self.api.picking_scan(self.receipt.id, "6260001000028")
		result = self.api.picking_validate(self.receipt.id)
		# Odoo asks whether to keep a backorder for what is missing
		self.assertIn("action", result)

	def test_count(self):
		self.assertEqual(self.api.scan(self.stock.barcode)["type"], "count") if self.stock.barcode else None
		for _i in range(3):
			data = self.api.count_scan(self.stock.id, "6260001000035")
		self.assertEqual(self.line(data, self.other)["counted"], 3)
		self.api.count_apply(self.stock.id)
		self.assertEqual(self.other.with_context(location=self.stock.id).qty_available, 3)

	def test_product(self):
		data = self.api.product("6260001000011")
		self.assertTrue(data["found"])
		self.assertEqual(data["name"], self.tea.display_name)
		self.assertFalse(self.api.product("nope")["found"])
