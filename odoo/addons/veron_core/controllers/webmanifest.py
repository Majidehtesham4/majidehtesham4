"""The installable app (PWA) of the web client as ERP-VERON: its name, icon, Persian and right to left.
Install it from the browser's menu («Install app» / «Add to Home screen») on a phone or a computer."""

from odoo.http import request

from odoo.addons.web.controllers.webmanifest import WebManifest

COLOR = "#5B2C83"


class VeronWebManifest(WebManifest):
	def _get_webmanifest(self):
		manifest = super()._get_webmanifest()
		name = request.env["ir.config_parameter"].sudo().get_param("web.web_app_name") or "ERP-VERON"
		if name == "Odoo":
			name = "ERP-VERON"
		manifest.update({
			"name": name,
			"short_name": name,
			"lang": "fa",
			"dir": "rtl",
			"background_color": COLOR,
			"theme_color": COLOR,
			"icons": [
				{"src": "/veron_core/static/img/veron-192.png", "sizes": "192x192", "type": "image/png"},
				{"src": "/veron_core/static/img/veron-512.png", "sizes": "512x512", "type": "image/png"},
				{"src": "/veron_core/static/img/veron-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
			],
		})
		return manifest

	def _icon_path(self):
		return "veron_core/static/img/veron-192.png"
