from odoo import fields, models

MADE_IN = [("iran", "Made in Iran"), ("imported", "Imported")]


class CarModel(models.Model):
	_name = "veron.car.model"
	_description = "Car Model"
	_order = "brand, name"

	brand = fields.Char(required=True)
	name = fields.Char("Model", required=True)
	made_in = fields.Selection(MADE_IN, default="iran", required=True)
	body_type = fields.Selection([("sedan", "Sedan"), ("hatchback", "Hatchback"), ("suv", "SUV"), ("crossover", "Crossover"),
		("pickup", "Pickup"), ("van", "Van"), ("coupe", "Coupe")])
	engine = fields.Char()
	engine_volume = fields.Integer("Engine Volume (cc)")
	cylinders = fields.Integer()
	power_hp = fields.Integer("Power (hp)")
	torque_nm = fields.Integer("Torque (Nm)")
	transmission = fields.Selection([("manual", "Manual"), ("automatic", "Automatic"), ("cvt", "CVT"), ("dct", "Dual-Clutch")], "Gearbox")
	gears = fields.Integer()
	fuel = fields.Selection([("petrol", "Petrol"), ("cng", "Petrol and CNG"), ("diesel", "Diesel"), ("hybrid", "Hybrid"),
		("electric", "Electric")], "Fuel")
	fuel_tank = fields.Integer("Fuel Tank (L)")
	drive = fields.Selection([("front", "Front-Wheel"), ("rear", "Rear-Wheel"), ("all", "All-Wheel")])
	seats = fields.Integer()
	note = fields.Text("Specifications")
	active = fields.Boolean(default=True)

	_brand_name = models.Constraint("unique (brand, name)", "This model is already in the list.")

	def _compute_display_name(self):
		for model in self:
			model.display_name = f"{model.brand} {model.name}"


class CarColor(models.Model):
	_name = "veron.car.color"
	_description = "Car Color"
	_order = "sequence, name"

	name = fields.Char(required=True, translate=True)
	color = fields.Char("Color Code")
	sequence = fields.Integer(default=10)


class BodyPart(models.Model):
	_name = "veron.body.part"
	_description = "Body Part"
	_order = "sequence, id"

	name = fields.Char(required=True, translate=True)
	sequence = fields.Integer(default=10)


class BodyCondition(models.Model):
	_name = "veron.body.condition"
	_description = "Body Condition"
	_order = "sequence, id"

	name = fields.Char(required=True, translate=True)
	color = fields.Char("Color Code")
	severity = fields.Selection([("low", "Low"), ("medium", "Medium"), ("high", "High")], default="low", required=True,
		help="How much it lowers the price")
	sequence = fields.Integer(default=10)


class InspectionItem(models.Model):
	_name = "veron.inspection.item"
	_description = "Inspection Item"
	_order = "section, sequence, id"

	name = fields.Char(required=True, translate=True)
	section = fields.Selection([("technical", "Technical"), ("interior", "Interior")], default="technical", required=True)
	measure = fields.Selection([("score", "Score out of 5"), ("percent", "Percent")], default="score", required=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)


SERVICE_CATEGORIES = [("preparation", "Preparation"), ("repair", "Repair"), ("paperwork", "Paperwork"), ("other", "Other")]


class VehicleService(models.Model):
	_name = "veron.vehicle.service"
	_description = "Vehicle Service"
	_order = "category, sequence, id"

	name = fields.Char(required=True, translate=True)
	category = fields.Selection(SERVICE_CATEGORIES, default="other", required=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)


class Parking(models.Model):
	_name = "veron.parking"
	_description = "Parking"

	name = fields.Char(required=True)
	address = fields.Char()
	capacity = fields.Integer()
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
	vehicle_ids = fields.One2many("veron.vehicle", "parking_id", domain=[("state", "not in", ("sold", "exited"))])
	occupied = fields.Integer(compute="_compute_occupied")
	active = fields.Boolean(default=True)

	def _compute_occupied(self):
		for parking in self:
			parking.occupied = len(parking.vehicle_ids)
