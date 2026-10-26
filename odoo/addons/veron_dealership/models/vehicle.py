from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import plate
from .car_lists import SERVICE_CATEGORIES

STATES = [
	("awaiting", "Awaiting Delivery"),
	("preparation", "In Preparation"),
	("ready", "Ready for Sale"),
	("reserved", "Reserved"),
	("sold", "Sold"),
	("exited", "Exited"),
]
DOCUMENTS = [
	("doc_ownership", "Ownership Document"),
	("doc_card", "Vehicle Card"),
	("doc_insurance", "Third-Party Insurance"),
	("doc_body_insurance", "Body Insurance"),
	("doc_spare_key", "Spare Key"),
	("doc_warranty", "Warranty"),
	("doc_fines_clear", "Fines Cleared"),
	("doc_tax_clear", "Toll Cleared"),
	("doc_technical_check", "Technical Inspection"),
]


class Vehicle(models.Model):
	_name = "veron.vehicle"
	_description = "Vehicle"
	_inherit = ["mail.thread", "mail.activity.mixin", "image.mixin", "website.published.mixin"]
	_order = "entry_date desc, id desc"
	_rec_names_search = ["name", "title", "plate", "chassis_number", "model_id.name", "model_id.brand"]

	name = fields.Char("Number", required=True, readonly=True, copy=False, default="/")
	title = fields.Char(compute="_compute_title", store=True)
	state = fields.Selection(STATES, default="awaiting", required=True, tracking=True, copy=False)
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	currency_id = fields.Many2one(related="company_id.currency_id")

	# The car
	model_id = fields.Many2one("veron.car.model", "Car Model", required=True, tracking=True)
	made_in = fields.Selection(related="model_id.made_in", store=True)
	year = fields.Char("Model Year", help="Shamsi for cars made in Iran, Gregorian for imported ones")
	color_id = fields.Many2one("veron.car.color", "Color")
	mileage = fields.Integer("Mileage (km)", tracking=True)
	chassis_number = fields.Char("Chassis Number", tracking=True)
	engine_number = fields.Char("Engine Number")
	plate_left = fields.Char("Plate: Two Digits", size=2)
	plate_letter = fields.Selection([(letter, letter) for letter in plate.LETTERS], "Plate: Letter")
	plate_middle = fields.Char("Plate: Three Digits", size=3)
	plate_city = fields.Char("Plate: City Code", size=2)
	plate = fields.Char(compute="_compute_plate", store=True, index=True)
	plate_html = fields.Html("Plate Number", compute="_compute_plate_html", sanitize=False)

	# Where it is
	entry_date = fields.Date("Entry Date", tracking=True)
	parking_id = fields.Many2one("veron.parking", "Parking")
	parking_spot = fields.Char("Spot")
	days_in_lot = fields.Integer("Days in the Lot", compute="_compute_days_in_lot")

	# Whose it is
	ownership = fields.Selection([("business", "Ours"), ("investor", "An Investor's"), ("customer", "Consignment")],
		default="business", required=True, tracking=True)
	owner_id = fields.Many2one("res.partner", "Owner", tracking=True, help="The investor or the customer who left the car to sell")
	investment_contract_id = fields.Many2one("veron.investment.contract", "Investment Contract",
		groups="veron_dealership.group_dealership_manager")
	commission_rate = fields.Float("Commission (%)", help="The showroom's share of the sale price of a consigned car")
	charge_costs_to_owner = fields.Boolean("Costs Paid by the Owner")

	# Prices
	purchase_date = fields.Date("Purchase Date", groups="veron_dealership.group_dealership_manager")
	purchase_price = fields.Monetary("Purchase Price", tracking=True, groups="veron_dealership.group_dealership_manager")
	seller_id = fields.Many2one("res.partner", "Bought From", groups="veron_dealership.group_dealership_manager")
	asking_price = fields.Monetary("Asking Price", tracking=True)
	minimum_price = fields.Monetary("Lowest Price", groups="veron_dealership.group_dealership_manager",
		help="Only a manager sells below it")

	# Documents, body and inspection
	doc_ownership = fields.Boolean("Ownership Document")
	doc_card = fields.Boolean("Vehicle Card")
	doc_insurance = fields.Boolean("Third-Party Insurance")
	doc_body_insurance = fields.Boolean("Body Insurance")
	doc_spare_key = fields.Boolean("Spare Key")
	doc_warranty = fields.Boolean("Warranty")
	doc_fines_clear = fields.Boolean("Fines Cleared")
	doc_tax_clear = fields.Boolean("Toll Cleared")
	doc_technical_check = fields.Boolean("Technical Inspection")
	documents_note = fields.Text("About the Documents")
	body_mark_ids = fields.One2many("veron.vehicle.body.mark", "vehicle_id", "Body")
	inspection_ids = fields.One2many("veron.vehicle.inspection", "vehicle_id", "Inspection")
	inspection_note = fields.Text("Expert's Opinion")
	inspection_score = fields.Float("Inspection Score (%)", compute="_compute_inspection_score")

	# Costs and the sale
	cost_ids = fields.One2many("veron.vehicle.cost", "vehicle_id", "Costs")
	preparation_total = fields.Monetary("Preparation", compute="_compute_costs")
	repair_total = fields.Monetary("Repairs", compute="_compute_costs")
	paperwork_total = fields.Monetary("Paperwork", compute="_compute_costs")
	costs_total = fields.Monetary("All Costs", compute="_compute_costs")
	customer_id = fields.Many2one("res.partner", "Customer", tracking=True)
	sale_date = fields.Date("Sale Date", tracking=True, copy=False)
	sale_price = fields.Monetary("Sale Price", tracking=True, copy=False)
	instalment_sale_id = fields.Many2one("veron.instalment.sale", "Instalment Sale", copy=False,
		groups="veron_dealership.group_dealership_user")
	profit = fields.Monetary(compute="_compute_profit", groups="veron_dealership.group_dealership_manager",
		help="Ours: the sale price less the purchase price and the costs. Consignment: the commission, less the costs we paid")
	exit_date = fields.Date("Exit Date", copy=False)
	delivered_to = fields.Char("Delivered To", copy=False)
	purchase_bill_id = fields.Many2one("account.move", "Purchase Bill", copy=False, readonly=True)
	sale_invoice_id = fields.Many2one("account.move", "Sale Invoice", copy=False, readonly=True)

	# Website
	photo_ids = fields.One2many("veron.vehicle.photo", "vehicle_id", "Photos")
	website_featured = fields.Boolean("Featured")
	website_show_price = fields.Boolean("Show the Price", default=True)
	website_show_report = fields.Boolean("Show the Inspection")
	website_headline = fields.Char("Headline")
	website_description = fields.Text("Description for the Site")
	lead_ids = fields.One2many("crm.lead", "veron_vehicle_id", "Inquiries", groups="veron_dealership.group_dealership_user")
	lead_count = fields.Integer(compute="_compute_lead_count")
	notes = fields.Text()

	_chassis_company = models.Constraint("unique (chassis_number, company_id)", "A car with this chassis number is already recorded.")

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get("name", "/") == "/":
				vals["name"] = self.env["ir.sequence"].next_by_code("veron.vehicle") or "/"
		return super().create(vals_list)

	@api.depends("model_id", "year", "color_id")
	def _compute_title(self):
		for car in self:
			car.title = " ".join(filter(None, (car.model_id.display_name, car.year, car.color_id.name)))

	def _compute_display_name(self):
		for car in self:
			car.display_name = " - ".join(filter(None, (car.title, car.plate or car.name)))

	@api.depends("plate_left", "plate_letter", "plate_middle", "plate_city")
	def _compute_plate(self):
		for car in self:
			car.plate = plate.text(car.plate_left, car.plate_letter, car.plate_middle, car.plate_city)

	@api.depends("plate")
	def _compute_plate_html(self):
		for car in self:
			parts = plate.parse(car.plate)
			if not parts:
				car.plate_html = False
				continue
			left, letter, middle, city = (escape(p.translate(plate.PERSIAN)) for p in parts)
			car.plate_html = Markup(
				'<span class="o_veron_plate" dir="ltr"><span class="o_veron_plate_flag">I.R.<br/>IRAN</span>'
				'<span class="o_veron_plate_number">%s<em>%s</em>%s</span>'
				'<span class="o_veron_plate_city"><small>ایران</small>%s</span></span>'
			) % (left, letter, middle, city)

	@api.constrains("plate_left", "plate_letter", "plate_middle", "plate_city")
	def _check_plate(self):
		for car in self:
			if any((car.plate_left, car.plate_letter, car.plate_middle, car.plate_city)) and not car.plate:
				raise ValidationError(_("The plate is two digits, a letter, three digits and the two-digit city code."))

	@api.onchange("plate_left", "plate_middle", "plate_city")
	def _onchange_plate_digits(self):
		for field in ("plate_left", "plate_middle", "plate_city"):
			if self[field]:
				self[field] = plate.latin(self[field])

	def _compute_days_in_lot(self):
		today = fields.Date.context_today(self)
		for car in self:
			end = car.exit_date or car.sale_date or today
			car.days_in_lot = (end - car.entry_date).days if car.entry_date else 0

	@api.depends("inspection_ids.score", "inspection_ids.measure")
	def _compute_inspection_score(self):
		for car in self:
			scores = [line.score / 5 * 100 if line.measure == "score" else line.score for line in car.inspection_ids if line.score]
			car.inspection_score = sum(scores) / len(scores) if scores else 0

	@api.depends("cost_ids.amount", "cost_ids.category")
	def _compute_costs(self):
		for car in self:
			totals = {category: 0.0 for category, _label in SERVICE_CATEGORIES}
			for cost in car.cost_ids:
				totals[cost.category or "other"] += cost.amount
			car.preparation_total = totals["preparation"]
			car.repair_total = totals["repair"]
			car.paperwork_total = totals["paperwork"]
			car.costs_total = sum(totals.values())

	@api.depends("sale_price", "purchase_price", "costs_total", "ownership", "commission_rate", "charge_costs_to_owner")
	def _compute_profit(self):
		for car in self:
			if car.ownership == "business":
				car.profit = car.sale_price - car.purchase_price - car.costs_total if car.sale_price else 0
			else:
				commission = car.sale_price * car.commission_rate / 100
				car.profit = commission - (0 if car.charge_costs_to_owner else car.costs_total)

	def _compute_lead_count(self):
		counts = dict(self.env["crm.lead"].sudo()._read_group([("veron_vehicle_id", "in", self.ids)], ["veron_vehicle_id"], ["__count"]))
		for car in self:
			car.lead_count = counts.get(car, 0)

	def _compute_website_url(self):
		for car in self:
			car.website_url = f"/showroom/{car.id}" if car.id else False

	# --- steps

	def _need(self, *states):
		for car in self:
			if car.state not in states:
				raise UserError(_("%(car)s is %(state)s.", car=car.display_name, state=dict(STATES)[car.state]))

	def action_receive(self):
		self._need("awaiting")
		for car in self:
			car.write({"state": "preparation", "entry_date": car.entry_date or fields.Date.context_today(self)})
		return True

	def action_ready(self):
		self._need("preparation", "reserved")
		for car in self:
			if not car.asking_price:
				raise UserError(_("Set the asking price of %s first.", car.display_name))
		self.write({"state": "ready"})
		return True

	def action_reserve(self):
		self._need("ready")
		if self.filtered(lambda car: not car.customer_id):
			raise UserError(_("Choose the customer the car is reserved for."))
		self.write({"state": "reserved"})
		return True

	def action_sell(self):
		self._need("ready", "reserved")
		manager = self.env.user.has_group("veron_dealership.group_dealership_manager")
		for car in self:
			if not car.customer_id or not car.sale_price:
				raise UserError(_("Enter the customer and the sale price of %s.", car.display_name))
			if not manager and car.sale_price < car.sudo().minimum_price:
				raise UserError(_("The sale price is below the lowest price; only a manager sells at it."))
			car.write({"state": "sold", "sale_date": car.sale_date or fields.Date.context_today(self), "website_published": False})
		return True

	def action_exit(self):
		self._need("sold")
		self.write({"state": "exited", "exit_date": fields.Date.context_today(self)})
		return True

	def action_back_to_ready(self):
		self._need("reserved")
		self.write({"state": "ready"})
		return True

	# --- accounting, as drafts for the accountant

	def _car_product(self):
		return self.env.ref("veron_dealership.product_vehicle")

	def _invoice_line(self, price, name=None, product=None):
		return (0, 0, {"product_id": (product or self._car_product()).id, "name": name or self._invoice_text(),
			"quantity": 1, "price_unit": price})

	def _invoice_text(self):
		return " - ".join(filter(None, (self.title, self.plate, self.chassis_number and _("Chassis %s", self.chassis_number))))

	def action_create_sale_invoice(self):
		self.ensure_one()
		if not self.customer_id or not self.sale_price:
			raise UserError(_("Enter the customer and the sale price first."))
		if self.ownership == "customer":
			lines = [self._invoice_line(self.sale_price * self.commission_rate / 100, _("Commission on %s", self._invoice_text()),
				self.env.ref("veron_dealership.product_commission"))]
			partner = self.owner_id
			if not partner:
				raise UserError(_("Enter the owner of the consigned car."))
		else:
			lines = [self._invoice_line(self.sale_price)]
			partner = self.customer_id
		self.sale_invoice_id = self.env["account.move"].create({
			"move_type": "out_invoice", "partner_id": partner.id, "invoice_line_ids": lines,
			"invoice_origin": self.name, "company_id": self.company_id.id,
		})
		return self._open_move(self.sale_invoice_id)

	def action_create_purchase_bill(self):
		self.ensure_one()
		if self.ownership != "business":
			raise UserError(_("Only a car of our own is bought."))
		if not self.seller_id or not self.purchase_price:
			raise UserError(_("Enter whom the car was bought from and its price first."))
		self.purchase_bill_id = self.env["account.move"].create({
			"move_type": "in_invoice", "partner_id": self.seller_id.id, "invoice_line_ids": [self._invoice_line(self.purchase_price)],
			"invoice_date": self.purchase_date, "invoice_origin": self.name, "company_id": self.company_id.id,
		})
		return self._open_move(self.purchase_bill_id)

	def action_create_cost_bills(self):
		"""A draft bill to each provider, for the costs not billed yet"""
		self.ensure_one()
		costs = self.cost_ids.filtered(lambda c: c.partner_id and not c.bill_id and c.amount)
		if not costs:
			raise UserError(_("No cost with a provider is left to bill."))
		bills = self.env["account.move"]
		for partner, partner_costs in costs.grouped("partner_id").items():
			bill = self.env["account.move"].create({
				"move_type": "in_invoice", "partner_id": partner.id, "invoice_origin": self.name, "company_id": self.company_id.id,
				"invoice_line_ids": [(0, 0, {"product_id": self.env.ref("veron_dealership.product_service").id,
					"name": f"{cost.service_id.name or cost.name} - {self._invoice_text()}", "quantity": 1, "price_unit": cost.amount})
					for cost in partner_costs],
			})
			partner_costs.bill_id = bill
			bills |= bill
		return self._open_move(bills)

	def _open_move(self, moves):
		action = {"type": "ir.actions.act_window", "res_model": "account.move", "name": _("Invoices")}
		if len(moves) == 1:
			return {**action, "view_mode": "form", "res_id": moves.id}
		return {**action, "view_mode": "list,form", "domain": [("id", "in", moves.ids)]}

	def action_open_leads(self):
		self.ensure_one()
		return {"type": "ir.actions.act_window", "res_model": "crm.lead", "name": _("Inquiries"), "view_mode": "list,form",
			"domain": [("veron_vehicle_id", "=", self.id)], "context": {"default_veron_vehicle_id": self.id}}

	def action_fill_inspection(self):
		"""The items of the inspection list, for the expert to score"""
		for car in self:
			present = car.inspection_ids.item_id
			items = self.env["veron.inspection.item"].search([("id", "not in", present.ids)])
			car.inspection_ids = [(0, 0, {"item_id": item.id}) for item in items]
		return True


class VehicleBodyMark(models.Model):
	_name = "veron.vehicle.body.mark"
	_description = "Body Condition of a Vehicle"

	vehicle_id = fields.Many2one("veron.vehicle", required=True, ondelete="cascade")
	part_id = fields.Many2one("veron.body.part", "Part", required=True)
	condition_id = fields.Many2one("veron.body.condition", "Condition", required=True)
	severity = fields.Selection(related="condition_id.severity")
	note = fields.Char()


class VehicleInspection(models.Model):
	_name = "veron.vehicle.inspection"
	_description = "Inspection Line"
	_order = "section, sequence, id"

	vehicle_id = fields.Many2one("veron.vehicle", required=True, ondelete="cascade")
	item_id = fields.Many2one("veron.inspection.item", "Item", required=True)
	section = fields.Selection(related="item_id.section", store=True)
	measure = fields.Selection(related="item_id.measure")
	sequence = fields.Integer(related="item_id.sequence", store=True)
	score = fields.Float(help="Out of 5, or a percent for the items measured in percent")
	comment = fields.Char()

	@api.constrains("score")
	def _check_score(self):
		for line in self:
			top = 5 if line.measure == "score" else 100
			if not 0 <= line.score <= top:
				raise ValidationError(_("The score of %(item)s is between 0 and %(top)s.", item=line.item_id.name, top=top))


class VehicleCost(models.Model):
	_name = "veron.vehicle.cost"
	_description = "Vehicle Cost"
	_order = "date desc, id desc"

	vehicle_id = fields.Many2one("veron.vehicle", required=True, ondelete="cascade")
	service_id = fields.Many2one("veron.vehicle.service", "Service")
	name = fields.Char("Description")
	category = fields.Selection(SERVICE_CATEGORIES, compute="_compute_category", store=True, readonly=False)
	date = fields.Date(default=fields.Date.context_today)
	partner_id = fields.Many2one("res.partner", "Provider")
	amount = fields.Monetary(required=True)
	currency_id = fields.Many2one(related="vehicle_id.currency_id")
	bill_id = fields.Many2one("account.move", "Bill", readonly=True, copy=False)

	@api.depends("service_id")
	def _compute_category(self):
		for cost in self:
			cost.category = cost.service_id.category or cost.category or "other"


class VehiclePhoto(models.Model):
	_name = "veron.vehicle.photo"
	_description = "Vehicle Photo"
	_inherit = ["image.mixin"]
	_order = "sequence, id"

	vehicle_id = fields.Many2one("veron.vehicle", required=True, ondelete="cascade")
	name = fields.Char()
	sequence = fields.Integer(default=10)
