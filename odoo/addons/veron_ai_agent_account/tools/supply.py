"""A draft purchase (a request for quotation) for what is short: made only when a person says so or the draft
invoice policy makes it, for a vendor and a warehouse that are clear, and never confirmed or sent here."""

from odoo.tools.translate import LazyTranslate

from odoo.addons.veron_ai_agent.services.registry import Plan, ToolAsks, ToolDenied, tool
from odoo.addons.veron_ai_agent.services.schema import strict_object
from odoo.addons.veron_ai_agent.tools.common import scoped

from .finance import FinanceTool

_lt = LazyTranslate(__name__)


@tool
class PurchaseDraftCreate(FinanceTool):
	code = "purchase_draft_create"
	name = _lt("Make a Draft Purchase")
	description = _lt("Makes a request for quotation (a draft purchase order) of products and counts, for a vendor "
		"and a receiving warehouse. A vendor not said is the one vendor set on all the products, else asked; a "
		"warehouse not said is the company's only one, else asked. It is never confirmed or sent here; «origin» "
		"links it to the sale it is for.")
	category = "draft"
	action = "draft"
	risk = "medium"
	models = ("purchase.order", "product.product", "res.partner")
	schema = strict_object({
		"partner_id": {"type": "integer", "minimum": 1, "description": "The vendor"},
		"warehouse_id": {"type": "integer", "minimum": 1, "description": "The warehouse it is received in"},
		"origin": {"type": "string", "maxLength": 200, "description": "The document it is for, e.g. the sale invoice"},
		"lines": {"type": "array", "minItems": 1, "maxItems": 50, "items": strict_object({
			"product_id": {"type": "integer", "minimum": 1},
			"quantity": {"type": "number", "exclusiveMinimum": 0},
		}, ["product_id", "quantity"])},
	}, ["lines"])

	def available(self, env):
		return "purchase.order" in env

	def _products(self, ctx, args):
		ids = [line["product_id"] for line in args["lines"]]
		model, domain = scoped(ctx, "product.product", [("id", "in", ids)])
		products = model.search(domain)
		if set(products.ids) != set(ids):
			raise ToolDenied(ctx.env._("A product is not in the agent's data."))
		return products

	def _vendor(self, ctx, args, products):
		"""The vendor said, or the one vendor set on every product; never guessed"""
		if args.get("partner_id"):
			model, domain = scoped(ctx, "res.partner", [("id", "=", args["partner_id"])])
			vendor = model.search(domain, limit=1)
			if not vendor:
				raise ToolDenied(ctx.env._("No such contact in the agent's data."))
			return vendor
		company = ctx.env.company
		sellers = products.seller_ids.filtered(lambda s: not s.company_id or s.company_id == company)
		vendors = {product.id: sellers.filtered(lambda s, p=product: s.product_tmpl_id == p.product_tmpl_id).partner_id
			for product in products}
		common = set.intersection(*(set(partners.ids) for partners in vendors.values())) if vendors else set()
		if all(len(partners) == 1 for partners in vendors.values()) and len(common) == 1:
			return ctx.env["res.partner"].browse(common.pop())
		known = sellers.partner_id
		question = ctx.env._("From which vendor? The vendors set on these products: %s.", ", ".join(known.mapped(
			"display_name"))) if known else ctx.env._("From which vendor? No vendor is set on these products; write its name.")
		raise ToolAsks(question, "partner_id", [(partner.id, partner.display_name) for partner in known[:8]])

	def _receipt(self, ctx, args):
		"""The receipt type of the warehouse said, or of the company's only warehouse; asked when there are several"""
		if "stock.picking.type" not in ctx.env:
			return None
		Type = ctx.env["stock.picking.type"]
		domain = [("code", "=", "incoming"), ("company_id", "=", ctx.env.company.id)]
		if args.get("warehouse_id"):
			found = Type.search(domain + [("warehouse_id", "=", args["warehouse_id"])], limit=1)
			if not found:
				raise ToolDenied(ctx.env._("That warehouse receives no purchases."))
			return found
		found = Type.search(domain)
		warehouses = found.warehouse_id
		if len(warehouses) <= 1:
			return found[:1] or None
		raise ToolAsks(ctx.env._("To which warehouse?"), "warehouse_id",
			[(warehouse.id, warehouse.display_name) for warehouse in warehouses[:8]])

	def _checked(self, ctx, args):
		ctx.check_model("purchase.order")
		products = self._products(ctx, args)
		return products, self._vendor(ctx, args, products), self._receipt(ctx, args)

	def plan(self, ctx, args):
		products, vendor, _receipt = self._checked(ctx, args)
		return Plan(summary=ctx.env._("Draft purchase from %(vendor)s: %(lines)s", vendor=vendor.display_name,
			lines=", ".join(f"{products.browse(line['product_id']).display_name} × {line['quantity']:g}"
				for line in args["lines"])), model="purchase.order", company_ids=[ctx.env.company.id])

	def execute(self, ctx, args, plan):
		products, vendor, receipt = self._checked(ctx, args)
		values = {"partner_id": vendor.id, "origin": args.get("origin") or False, "company_id": ctx.env.company.id,
			"order_line": [(0, 0, {"product_id": line["product_id"], "product_qty": line["quantity"]})
				for line in args["lines"]]}
		if receipt:
			values["picking_type_id"] = receipt.id
		order = ctx.env["purchase.order"].create(values)
		ctx.link(order)
		return {"purchase_id": order.id, "purchase": order.display_name, "vendor": vendor.display_name,
			"warehouse": receipt.warehouse_id.display_name if receipt else "", "origin": order.origin or "",
			"lines": [{"product": line.product_id.display_name, "quantity": line.product_qty, "price": round(line.price_unit, 2)}
				for line in order.order_line],
			"state": ctx.env._("request for quotation (draft); not confirmed nor sent"), "confirmed": False}
