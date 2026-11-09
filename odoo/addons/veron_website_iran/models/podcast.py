from odoo import api, fields, models
from odoo.tools import html2plaintext


class PodcastEpisode(models.Model):
	"""An episode of the website's podcast, with its audio as a file or an address"""

	_name = "veron.podcast.episode"
	_description = "Podcast Episode"
	_inherit = ["website.published.mixin"]
	_order = "date desc, id desc"

	name = fields.Char("Title", required=True, translate=True)
	description = fields.Html(translate=True)
	date = fields.Date(required=True, default=fields.Date.context_today)
	audio = fields.Binary(attachment=True)
	audio_name = fields.Char()
	audio_url = fields.Char("Audio Address", help="Instead of a file, the address of the audio elsewhere")
	duration = fields.Char(help="As «24:30»")
	image = fields.Image(max_width=1024, max_height=1024)
	website_id = fields.Many2one("website", ondelete="cascade")

	def _compute_website_url(self):
		for episode in self:
			episode.website_url = f"/podcast/{episode.id}" if episode.id else "/podcast"

	def _audio_address(self):
		self.ensure_one()
		if self.audio_url:
			return self.audio_url
		return f"/web/content/veron.podcast.episode/{self.id}/audio/{self.audio_name or 'episode.mp3'}" if self.audio else ""

	def _summary(self):
		return html2plaintext(self.description or "")[:400]

	@api.model
	def _published(self, website):
		return self.sudo().search([("is_published", "=", True), "|", ("website_id", "=", False),
			("website_id", "=", website.id)])
