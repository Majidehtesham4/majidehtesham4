from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestKardex(TransactionCase):
	def test_card_of_a_product(self):
		warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
		stock = warehouse.lot_stock_id
		shelf = self.env["stock.location"].create({"name": "قفسه", "location_id": stock.id, "usage": "internal"})
		supplier = self.env.ref("stock.stock_location_suppliers")
		customer = self.env.ref("stock.stock_location_customers")
		product = self.env["product.product"].create({"name": "پیچ", "is_storable": True, "standard_price": 1000})

		def move(source, dest, quantity, date):
			done = self.env["stock.move"].create({"product_id": product.id, "product_uom_qty": quantity,
				"product_uom": product.uom_id.id, "location_id": source.id, "location_dest_id": dest.id})
			done._action_confirm()
			done.quantity = quantity
			done.picked = True
			done._action_done()
			done.date = date
			return done

		move(supplier, stock, 100, "2026-09-01 08:00:00")
		move(supplier, stock, 50, "2026-10-01 08:00:00")
		move(stock, shelf, 30, "2026-10-02 08:00:00")
		move(stock, customer, 20, "2026-10-03 08:00:00")
		card = self.env["veron.stock.kardex"].create({"product_id": product.id, "warehouse_id": warehouse.id,
			"date_from": "2026-09-23", "date_to": "2026-10-22"})
		card.action_compute()
		self.assertEqual(card.opening, 100)
		self.assertEqual([(l.quantity_in, l.quantity_out, l.balance) for l in card.line_ids], [(50, 0, 150), (0, 20, 130)],
			"a move inside the warehouse is neither in nor out")
		self.assertEqual(card.closing, 130)
		shelf_card = self.env["veron.stock.kardex"].create({"product_id": product.id, "location_id": shelf.id,
			"date_from": "2026-09-23", "date_to": "2026-10-22"})
		shelf_card.action_compute()
		self.assertEqual((shelf_card.opening, shelf_card.closing), (0, 30))
		html = self.env["ir.actions.report"]._render_qweb_html("veron_stock_kardex.report_kardex", card.ids)[0].decode()
		self.assertIn("کاردکس کالا", html)
