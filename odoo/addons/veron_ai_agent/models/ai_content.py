from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError


class AiContent(models.Model):
	"""A text or an image an agent drafted. It is not published until a person approves it; an image made by
	AI is marked as such, and is never taken for a photo of the real product."""

	_name = "veron.ai.content"
	_description = "Agent Content Draft"
	_inherit = ["mail.thread"]
	_order = "id desc"

	name = fields.Char("Title", required=True)
	kind = fields.Selection([("product_description", "Product Description"), ("web_page", "Web Page Text"),
		("seo", "Search-Engine Title and Description"), ("marketing", "Marketing Text"), ("image", "Image")],
		required=True, default="product_description")
	body = fields.Html(sanitize=True)
	meta_title = fields.Char("Search-Engine Title")
	meta_description = fields.Char("Search-Engine Description")
	source_id = fields.Many2one("veron.ai.source", "Image", readonly=True)
	image = fields.Binary(related="source_id.attachment_id.datas", string="Image File")
	ai_generated = fields.Boolean("Made by AI", default=True, readonly=True)
	product_tmpl_id = fields.Many2one("product.template", "Product", ondelete="cascade")
	state = fields.Selection([("draft", "Draft"), ("published", "Published"), ("rejected", "Rejected")], default="draft",
		tracking=True, readonly=True)
	run_id = fields.Many2one("veron.ai.run", readonly=True, ondelete="set null")
	agent_id = fields.Many2one(related="run_id.agent_id", store=True)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

	def action_reject(self):
		self.write({"state": "rejected"})

	def _publish(self):
		"""Called by the publish tool, after a person's approval: the text or the image goes to the product"""
		for content in self:
			if content.state != "draft":
				raise UserError(_("%s is not a draft.", content.name))
			product = content.product_tmpl_id
			if not product:
				raise UserError(_("%s has no product to publish on.", content.name))
			if content.kind == "product_description":
				field = "website_description" if "website_description" in product._fields else "description_sale"
				product[field] = content.body if field == "website_description" else Markup(content.body or "").striptags()
			elif content.kind == "seo":
				if "website_meta_title" not in product._fields:
					raise UserError(_("The website is not installed."))
				product.write({"website_meta_title": content.meta_title, "website_meta_description": content.meta_description})
			elif content.kind == "image":
				if "product.image" not in self.env:
					raise UserError(_("Extra product images need the online shop."))
				self.env["product.image"].create({"name": _("Made by AI: %s", content.name)[:120],
					"product_tmpl_id": product.id, "image_1920": content.image})
			else:
				raise UserError(_("This kind of content is copied by hand."))
			content.state = "published"
			content.message_post(body=_("Published on %s", product.display_name))
