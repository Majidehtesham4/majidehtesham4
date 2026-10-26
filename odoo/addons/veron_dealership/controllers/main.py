from odoo import http
from odoo.http import request

SHOWN = ("ready", "reserved")


class Showroom(http.Controller):
	def _cars(self):
		return request.env["veron.vehicle"].sudo().search(
			[("website_published", "=", True), ("state", "in", SHOWN)], order="website_featured desc, entry_date desc")

	def _car(self, car_id):
		car = request.env["veron.vehicle"].sudo().browse(car_id).exists()
		if not car or not car.website_published or car.state not in SHOWN:
			raise request.not_found()
		return car

	@http.route("/showroom", type="http", auth="public", website=True, sitemap=True)
	def showroom(self, model=None, **kw):
		cars = self._cars()
		models = cars.model_id
		if model and model.isdigit():
			cars = cars.filtered(lambda c: c.model_id.id == int(model))
		return request.render("veron_dealership.showroom_page", {"cars": cars, "models": models, "model": model})

	@http.route("/showroom/<int:car_id>", type="http", auth="public", website=True, sitemap=False)
	def car(self, car_id, sent=None, **kw):
		return request.render("veron_dealership.car_page", {"car": self._car(car_id), "sent": sent})

	@http.route("/showroom/image/<int:car_id>", type="http", auth="public", website=True, sitemap=False)
	def car_image(self, car_id, **kw):
		car = self._car(car_id)
		return request.env["ir.binary"]._get_image_stream_from(car, "image_1024").get_response()

	@http.route("/showroom/photo/<int:photo_id>", type="http", auth="public", website=True, sitemap=False)
	def photo(self, photo_id, **kw):
		photo = request.env["veron.vehicle.photo"].sudo().browse(photo_id).exists()
		if not photo:
			raise request.not_found()
		self._car(photo.vehicle_id.id)
		return request.env["ir.binary"]._get_image_stream_from(photo, "image_1024").get_response()

	@http.route("/showroom/<int:car_id>/inquiry", type="http", auth="public", website=True, methods=["POST"], sitemap=False)
	def inquiry(self, car_id, name="", phone="", message="", **kw):
		car = self._car(car_id)
		name, phone = name.strip()[:100], phone.strip()[:30]
		if name and phone:
			request.env["crm.lead"].sudo().create({
				"name": f"{car.title} - {name}",
				"contact_name": name,
				"phone": phone,
				"description": (message or "")[:2000],
				"veron_vehicle_id": car.id,
				"company_id": car.company_id.id,
				"type": "lead" if request.env.user.has_group("crm.group_use_lead") else "opportunity",
			})
		return request.redirect(f"/showroom/{car.id}?sent=1")
