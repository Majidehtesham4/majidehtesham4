import logging
from xml.sax.saxutils import escape

import requests

from odoo import _, http
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)
NESHAN_STATIC = "https://api.neshan.org/v2/static"


class MobileLogin(http.Controller):
	"""Login with a mobile number: the number, then the code sent to it. Only the code's hash is kept; the person is
	logged in by Odoo's own authentication, with a token good once"""

	def _render(self, **values):
		return request.render("veron_website_iran.mobile_login", values)

	@http.route("/web/login/mobile", type="http", auth="public", website=True, methods=["GET", "POST"], sitemap=False)
	def mobile_login(self, mobile=None, code=None, redirect=None, **kwargs):
		if not request.website.veron_otp_login:
			return request.redirect("/web/login")
		Code = request.env["veron.login.code"].sudo()
		values = {"mobile": mobile or "", "redirect": redirect or ""}
		if request.httprequest.method != "POST":
			return self._render(**values)
		if not code:
			try:
				values["mobile"] = Code._send(mobile, request.httprequest.remote_addr)
				values["sent"] = True
			except UserError as error:
				values["error"] = str(error)
			return self._render(**values)
		try:
			user, token = Code._check(mobile, code)
			request.env.cr.commit()  # the code is used even if the login below fails
			request.session.authenticate(request.env, {"type": "veron_otp", "login": user.login, "token": token})
		except AccessDenied as error:
			request.env.cr.commit()  # the try is counted
			values.update(sent=True, error=str(error) if str(error) != "Access Denied" else _("The code is not right."))
			return self._render(**values)
		return request.redirect(redirect if (redirect or "").startswith("/") else "/my")


class NeshanMap(http.Controller):
	@http.route("/veron/neshan/map", type="http", auth="public", website=True, sitemap=False)
	def neshan_map(self, lat="35.6997", lng="51.3380", zoom="15", **kwargs):
		"""A page of the map around a point, for the map block of the website; the Neshan key stays here"""
		try:
			lat, lng, zoom = float(lat), float(lng), max(min(int(zoom), 18), 3)
		except ValueError:
			return request.not_found()
		link = f"https://neshan.org/maps/@{lat},{lng},{zoom}z"
		html = (f'<html><body style="margin:0"><a href="{escape(link)}" target="_blank" rel="noopener">'
			f'<img src="/veron/neshan/static?lat={lat}&amp;lng={lng}&amp;zoom={zoom}" alt="Neshan" '
			'style="width:100%;height:100%;object-fit:cover;border:0"/></a></body></html>')
		return request.make_response(html, [("Content-Type", "text/html; charset=utf-8")])

	@http.route("/veron/neshan/static", type="http", auth="public", website=True, sitemap=False)
	def neshan_static(self, lat="35.6997", lng="51.3380", zoom="15", **kwargs):
		key = request.website.sudo().veron_neshan_key
		if not key:
			return request.make_response(_("Set the Neshan key of the website."), [("Content-Type", "text/plain; charset=utf-8")],
				status=404)
		try:
			params = {"key": key, "type": "neshan", "zoom": max(min(int(zoom), 18), 3), "center": f"{float(lat)},{float(lng)}",
				"width": 800, "height": 450, "marker": "red"}
			answer = requests.get(NESHAN_STATIC, params=params, timeout=15)
		except (ValueError, requests.exceptions.RequestException) as error:
			_logger.warning("Neshan map not drawn: %s", error)
			return request.not_found()
		if answer.status_code != 200:
			return request.not_found()
		return request.make_response(answer.content, [("Content-Type", answer.headers.get("Content-Type", "image/png")),
			("Cache-Control", "public, max-age=86400")])


class Podcast(http.Controller):
	@http.route(["/podcast", "/podcast/<int:episode_id>"], type="http", auth="public", website=True)
	def podcast(self, episode_id=None, **kwargs):
		episodes = request.env["veron.podcast.episode"]._published(request.website)
		episode = episodes.filtered(lambda e: e.id == episode_id) if episode_id else episodes.browse()
		if episode_id and not episode:
			return request.not_found()
		return request.render("veron_website_iran.podcast_page", {"episodes": episodes, "episode": episode})

	@http.route("/podcast/rss.xml", type="http", auth="public", website=True, sitemap=False)
	def podcast_rss(self, **kwargs):
		website = request.website
		base = website.get_base_url()
		items = []
		for episode in request.env["veron.podcast.episode"]._published(website):
			audio = episode._audio_address()
			if not audio:
				continue
			url = audio if audio.startswith("http") else base + audio
			items.append(f"<item><title>{escape(episode.name)}</title><description>{escape(episode._summary())}</description>"
				f'<enclosure url="{escape(url)}" type="audio/mpeg" length="0"/><guid>{base}/podcast/{episode.id}</guid>'
				f"<pubDate>{episode.date.strftime('%a, %d %b %Y 00:00:00 +0000')}</pubDate></item>")
		feed = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(website.name or "")}</title>'
			f"<link>{base}/podcast</link><description>{escape(website.name or '')}</description>{''.join(items)}</channel></rss>")
		return request.make_response(feed, [("Content-Type", "application/rss+xml; charset=utf-8")])
