"""Drafts: texts and images for products and marketing, kept as drafts; publishing them is a sensitive action
a person approves. A transfer between warehouses is made as a draft, never confirmed by the agent."""

from markupsafe import Markup, escape

from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from ..services.registry import Plan, Tool, ToolDenied, tool
from ..services.schema import strict_object

_lt = LazyTranslate(__name__)

KINDS = ["product_description", "web_page", "seo", "marketing"]


def _product(ctx, product_id):
	ctx.check_model("product.template")
	product = ctx.env["product.template"].search(ctx.domain("product.template") & Domain("id", "=", product_id), limit=1)
	if not product:
		raise ToolDenied(ctx.env._("No such product in the agent's data."))
	return product


@tool
class ContentDraft(Tool):
	code = "content_draft"
	name = _lt("Save a Text Draft")
	description = _lt("Saves a text the agent wrote (a product description, web page text, search-engine title and "
		"description, a marketing text) as a draft. Nothing is published.")
	category = "draft"
	action = "draft"
	schema = strict_object({
		"kind": {"type": "string", "enum": KINDS},
		"title": {"type": "string", "minLength": 2, "maxLength": 200},
		"body": {"type": "string", "maxLength": 20000},
		"meta_title": {"type": "string", "maxLength": 70},
		"meta_description": {"type": "string", "maxLength": 170},
		"product_id": {"type": "integer", "minimum": 1, "description": "A product template id, when the text is for a product"},
	}, ["kind", "title"])

	def plan(self, ctx, args):
		if args.get("product_id"):
			_product(ctx, args["product_id"])
		return Plan(summary=ctx.env._("Draft: %s", args["title"]), model="veron.ai.content")

	def execute(self, ctx, args, plan):
		from ..models.ai_run import markdown_html

		product = _product(ctx, args["product_id"]) if args.get("product_id") else None
		content = ctx.env["veron.ai.content"].sudo().create({
			"name": args["title"], "kind": args["kind"], "body": markdown_html(args.get("body") or ""),
			"meta_title": args.get("meta_title"), "meta_description": args.get("meta_description"),
			"product_tmpl_id": product.id if product else False, "run_id": ctx.run.id, "company_id": ctx.env.company.id,
		})
		ctx.link(content)
		return {"draft_id": content.id, "draft": content.name, "published": False}


@tool
class ImageDraft(Tool):
	code = "image_draft"
	name = _lt("Make a Draft Image")
	description = _lt("Makes an image with the image generation provider from a description, kept as a draft marked "
		"'made by AI'. It is never a photo of the real product and is not published.")
	category = "draft"
	action = "draft"
	risk = "medium"
	schema = strict_object({
		"prompt": {"type": "string", "minLength": 5, "maxLength": 2000},
		"title": {"type": "string", "minLength": 2, "maxLength": 200},
		"product_id": {"type": "integer", "minimum": 1},
		"size": {"type": "string", "enum": ["1024x1024", "1024x1536", "1536x1024"]},
	}, ["prompt", "title"])

	def plan(self, ctx, args):
		if not ctx.provider("image"):
			raise ToolDenied(ctx.env._("No image generation provider is set."))
		if args.get("product_id"):
			_product(ctx, args["product_id"])
		return Plan(summary=ctx.env._("Draft image: %s", args["title"]))

	def execute(self, ctx, args, plan):
		provider = ctx.provider("image")
		data = provider._adapter().generate_image(args["prompt"], args.get("size") or "1024x1024")
		provider._mark()
		source = ctx.env["veron.ai.source"].sudo()._from_upload(f"{args['title']}.png", data, purpose="product_image",
			kinds=("image",))
		source.ai_generated = True
		product = _product(ctx, args["product_id"]) if args.get("product_id") else None
		content = ctx.env["veron.ai.content"].sudo().create({"name": args["title"], "kind": "image", "source_id": source.id,
			"product_tmpl_id": product.id if product else False, "run_id": ctx.run.id, "company_id": ctx.env.company.id,
			"body": Markup("<p>%s</p>") % escape(args["prompt"])})
		ctx.link(content)
		return {"draft_id": content.id, "made_by_ai": True, "published": False}


@tool
class ContentPublish(Tool):
	code = "content_publish"
	name = _lt("Publish a Draft")
	description = _lt("Publishes a draft text or image on its product (the website description, the search-engine fields, "
		"or an extra image marked 'made by AI'). Publishing is a sensitive action a person approves.")
	category = "execute"
	action = "execute"
	risk = "high"
	sensitive = "publish"
	schema = strict_object({"draft_id": {"type": "integer", "minimum": 1}}, ["draft_id"])

	def _content(self, ctx, args):
		content = ctx.env["veron.ai.content"].sudo().browse(args["draft_id"]).exists()
		if not content or content.state != "draft" or content.company_id not in ctx.env.companies:
			raise ToolDenied(ctx.env._("No such draft."))
		if content.product_tmpl_id:
			_product(ctx, content.product_tmpl_id.id)
		return content

	def plan(self, ctx, args):
		content = self._content(ctx, args)
		return Plan(summary=ctx.env._("Publish %(draft)s on %(product)s", draft=content.name,
			product=content.product_tmpl_id.display_name or "-"), model="veron.ai.content", res_ids=content.ids,
			company_ids=content.company_id.ids)

	def execute(self, ctx, args, plan):
		content = self._content(ctx, args)
		# The product is written with the rights of the person who approved
		content.with_env(ctx.env)._publish()
		return {"published": content.name, "on": content.product_tmpl_id.display_name}


@tool
class StockTransferDraft(Tool):
	code = "stock_transfer_draft"
	name = _lt("Draft Transfer Between Warehouses")
	description = _lt("Makes a draft internal transfer of a product from one warehouse to another. It is not confirmed or done.")
	category = "draft"
	action = "draft"
	models = ("stock.picking",)
	schema = strict_object({
		"product_id": {"type": "integer", "minimum": 1},
		"quantity": {"type": "number", "minimum": 0.001, "maximum": 1000000},
		"from_warehouse_id": {"type": "integer", "minimum": 1},
		"to_warehouse_id": {"type": "integer", "minimum": 1},
	}, ["product_id", "quantity", "from_warehouse_id", "to_warehouse_id"])

	def _records(self, ctx, args):
		ctx.check_model("stock.picking")
		Warehouse = ctx.env["stock.warehouse"]
		source, target = Warehouse.browse(args["from_warehouse_id"]).exists(), Warehouse.browse(args["to_warehouse_id"]).exists()
		product = ctx.env["product.product"].browse(args["product_id"]).exists()
		if not source or not target or source == target or not product:
			raise ToolDenied(ctx.env._("Give a product and two different warehouses."))
		if source.company_id != target.company_id:
			raise ToolDenied(ctx.env._("A transfer stays within one company."))
		return source, target, product

	def plan(self, ctx, args):
		source, target, product = self._records(ctx, args)
		return Plan(summary=ctx.env._("Draft transfer of %(qty)s %(product)s from %(source)s to %(target)s", qty=args["quantity"],
			product=product.display_name, source=source.name, target=target.name), model="stock.picking",
			company_ids=source.company_id.ids)

	def execute(self, ctx, args, plan):
		source, target, product = self._records(ctx, args)
		picking_type = target.int_type_id
		picking = ctx.env["stock.picking"].create({
			"picking_type_id": picking_type.id, "location_id": source.lot_stock_id.id,
			"location_dest_id": target.lot_stock_id.id, "origin": ctx.run.sudo().name,
			"move_ids": [(0, 0, {"product_id": product.id, "product_uom_qty": args["quantity"], "product_uom": product.uom_id.id,
				"location_id": source.lot_stock_id.id, "location_dest_id": target.lot_stock_id.id})],
		})
		ctx.link(picking)
		return {"transfer": picking.name, "state": picking.state}
