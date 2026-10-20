"""The showroom website: the cars a customer may see, each car's page, the instalment calculator
and the customer's requests.

Only cars ticked «Show on the Website» and still in the lot are shown, and only what a buyer may
know: never the purchase price, the lowest price accepted, the owner or the books.
"""

import re
from html import unescape

import frappe
from frappe import _
from frappe.utils import cint, escape_html, flt, getdate, nowdate

from iran_erp.business import trade_profile
from iran_erp.iran_dealership.doctype.iran_car_inquiry.iran_car_inquiry import normal_mobile
from iran_erp.iran_dealership.doctype.iran_car_model.iran_car_model import spec_features, spec_rows
from iran_erp.iran_dealership.doctype.iran_instalment_sale.iran_instalment_sale import calculate
from iran_erp.iran_dealership.doctype.iran_showroom_settings.iran_showroom_settings import month_options
from iran_erp.utils.jalali import to_persian_digits

PUBLIC = ("Ready for Sale", "Reserved", "In Preparation")
STATUS_LABEL = {"Ready for Sale": "آماده تحویل", "Reserved": "رزرو شده", "In Preparation": "به‌زودی"}
DOCUMENTS = (
	"doc_ownership",
	"doc_card",
	"doc_insurance",
	"doc_body_insurance",
	"doc_spare_key",
	"doc_warranty",
	"doc_fines_clear",
	"doc_tax_clear",
	"doc_technical_check",
)
LIST_FIELDS = (
	"name",
	"title",
	"car_model",
	"made_in",
	"year",
	"color",
	"mileage",
	"status",
	"asking_price",
	"website_show_price",
	"website_headline",
	"featured",
	"branch",
)


def esc(value) -> str:
	"""Text typed by staff or customers, made safe for the page (the website's templates do not
	escape on their own)."""
	return escape_html(str(value or ""))


def digits_only(value) -> str:
	"""A phone or WhatsApp number for a tel: or wa.me link: digits and a leading +."""
	value = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
	return re.sub(r"[^\d+]", "", value)


def web_link(value) -> str:
	"""Only http(s) addresses become links."""
	value = str(value or "").strip()
	return esc(value) if re.match(r"^https?://", value) else ""


def settings() -> frappe._dict:
	"""The showroom's settings, its name and contacts, and the experts a customer may call."""
	s = frappe.get_cached_doc("Iran Showroom Settings")
	trade = trade_profile()

	def value(field, default):
		# Settings never saved have no values yet: the field's default stands
		return default if s.get(field) in (None, "") else s.get(field)

	return frappe._dict(
		enabled=cint(value("enabled", 1)),
		title=esc(s.site_title or trade.name),
		tagline=esc(s.tagline),
		hero_image=esc(s.hero_image),
		logo=esc(trade.logo),
		show_prices=cint(value("show_prices", 1)),
		toman=value("price_unit", "Toman") == "Toman",
		monthly_rate=flt(value("monthly_rate", 4)),
		months=month_options(value("months_options", "6,10,12,18,24")) or [12],
		min_down_percent=flt(value("min_down_percent", 30)),
		phone=digits_only(s.phone or trade.phone),
		whatsapp=digits_only(s.whatsapp).lstrip("+"),
		instagram=esc((s.instagram or "").strip().lstrip("@")),
		address=esc(s.address or trade.address),
		map_link=web_link(s.map_link),
		working_hours=esc(s.working_hours),
		experts=[
			{
				"full_name": esc(e.full_name),
				"job_title": esc(e.job_title),
				"mobile": digits_only(e.mobile),
				"whatsapp": digits_only(e.whatsapp).lstrip("+"),
				"photo": esc(e.photo),
				"branch": esc(e.branch),
			}
			for e in s.experts
		],
	)


def price_text(value, s=None) -> str:
	"""«۱٬۶۸۰٬۰۰۰٬۰۰۰ تومان»: the unit the showroom chose, Persian digits."""
	s = s or settings()
	amount = flt(value) / (10 if s.toman else 1)
	return to_persian_digits(f"{round(amount):,}").replace(",", "٬") + (" تومان" if s.toman else " ریال")


def _colors() -> dict:
	"""Colour name → «#rrggbb»; anything else is left out, since it goes into a style attribute."""
	return {
		name: code
		for name, code in frappe.get_all("Iran Car Color", fields=["name", "color_code"], as_list=True)
		if re.fullmatch(r"#[0-9a-fA-F]{3,8}", code or "")
	}


def _models() -> dict:
	return {
		m.name: m
		for m in frappe.get_all("Iran Car Model", fields=["name", "brand", "model", "body_type", "model_3d"])
	}


def _covers(names) -> dict:
	covers = {}
	for row in frappe.get_all(
		"Iran Vehicle Photo",
		filters={"parent": ("in", names), "parenttype": "Iran Vehicle"},
		fields=["parent", "image"],
		order_by="idx asc",
	):
		covers.setdefault(row.parent, row.image)
	return covers


def list_cars(args: dict | None = None) -> dict:
	"""The cars on the website with what the filters ask for, featured first, newest next."""
	args = frappe._dict(args or {})
	s = settings()
	models, colors = _models(), _colors()
	filters = {"show_on_website": 1, "status": ("in", PUBLIC)}
	if args.get("branch"):
		filters["branch"] = args.branch
	cars = frappe.get_all(
		"Iran Vehicle", filters=filters, fields=list(LIST_FIELDS), order_by="featured desc, entry_date desc"
	)
	brands = sorted({models[c.car_model].brand for c in cars if c.car_model in models})
	body_types = sorted({models[c.car_model].body_type for c in cars if c.car_model in models} - {None, ""})
	query = (args.get("q") or "").strip()
	price_unit = 10 if s.toman else 1
	low = flt(args.get("min_price")) * price_unit
	high = flt(args.get("max_price")) * price_unit

	def wanted(car, model):
		if args.get("brand") and model.brand != args.brand:
			return False
		if args.get("body") and model.body_type != args.body:
			return False
		if args.get("made_in") and car.made_in != args.made_in:
			return False
		if query and query not in (car.title or ""):
			return False
		if low and flt(car.asking_price) < low:
			return False
		if high and flt(car.asking_price) > high:
			return False
		return True

	shown = []
	for car in cars:
		model = models.get(car.car_model) or frappe._dict(brand="", model=car.car_model, body_type="")
		if not wanted(car, model):
			continue
		show_price = s.show_prices and cint(car.website_show_price) and flt(car.asking_price)
		shown.append(
			{
				"name": car.name,
				"brand": esc(model.brand),
				"model": esc(model.model),
				"year": esc(to_persian_digits(car.year or "")),
				"color": esc(car.color),
				"color_code": colors.get(car.color) or "#9aa4b2",
				"mileage": to_persian_digits(f"{cint(car.mileage):,}").replace(",", "٬"),
				"status": car.status,
				"status_label": STATUS_LABEL.get(car.status, ""),
				"price": price_text(car.asking_price, s) if show_price else "",
				"price_value": flt(car.asking_price) if show_price else 0,
				"headline": esc(car.website_headline),
				"featured": cint(car.featured),
			}
		)
	order = args.get("sort")
	if order in ("price_asc", "price_desc"):
		shown.sort(
			key=lambda c: (not c["price_value"], c["price_value"] * (1 if order == "price_asc" else -1))
		)
	covers = _covers([c["name"] for c in shown])
	for car in shown:
		car["cover"] = esc(covers.get(car["name"], ""))
	return {
		"cars": shown,
		"brands": [esc(b) for b in brands],
		"body_types": [esc(b) for b in body_types],
		"count": len(shown),
	}


def public_car(name: str) -> frappe.Document:
	"""The car, if the website may show it; otherwise «page not found»."""
	if not name or not frappe.db.exists("Iran Vehicle", name):
		raise frappe.PageDoesNotExistError
	car = frappe.get_doc("Iran Vehicle", name)
	if not cint(car.show_on_website) or car.status not in PUBLIC:
		raise frappe.PageDoesNotExistError
	return car


def car_page(name: str) -> dict:
	"""Everything the car's page shows, and nothing a buyer should not see."""
	from iran_erp.iran_dealership.printing import body_svg

	s = settings()
	car = public_car(name)
	model = (
		frappe.db.get_value(
			"Iran Car Model", car.car_model, ["brand", "model", "body_type", "model_3d"], as_dict=True
		)
		or frappe._dict()
	)
	show_price = bool(s.show_prices and cint(car.website_show_price) and flt(car.asking_price))
	report = cint(car.website_show_report)
	marks = {}
	for row in car.body_marks:
		marks.setdefault(esc(row.body_part), []).append(
			{"condition": esc(row.condition), "description": esc(row.description)}
		)
	days = (getdate(nowdate()) - getdate(car.entry_date)).days if car.entry_date else 0
	similar = [c for c in list_cars({"brand": model.get("brand")})["cars"] if c["name"] != car.name][:4]
	return {
		"name": car.name,
		"title": esc(f"{model.get('brand', '')} {model.get('model', '')}".strip() or car.title),
		"brand": esc(model.get("brand")),
		"model": esc(model.get("model")),
		"body_type": model.get("body_type") or "",
		"model_3d": model.get("model_3d") or "",
		"year": esc(to_persian_digits(car.year or "")),
		"made_in": car.made_in,
		"color": esc(car.color),
		"color_code": _colors().get(car.color) or "#9aa4b2",
		"mileage": to_persian_digits(f"{cint(car.mileage):,}").replace(",", "٬"),
		"plate_city": esc(to_persian_digits((car.plate or "").split(" ")[-1])) if car.plate else "",
		"status": car.status,
		"status_label": STATUS_LABEL.get(car.status, ""),
		"headline": esc(car.website_headline),
		"description": esc(car.website_description),
		"specs": [{"label": esc(r["label"]), "value": esc(r["value"])} for r in spec_rows(car.car_model)],
		"features": [
			esc(line)
			for line in dict.fromkeys(
				[
					*spec_features(car.car_model),
					*(line.strip() for line in (car.website_features or "").splitlines() if line.strip()),
				]
			)
		],
		"photos": [{"image": esc(p.image), "caption": esc(p.caption)} for p in car.photos],
		"show_price": show_price,
		"price": price_text(car.asking_price, s) if show_price else "",
		"price_value": flt(car.asking_price) if show_price else 0,
		"report": report,
		"body_svg": body_svg(car, 220) if report else "",
		"body_marks": marks if report else {},
		"inspection": [
			{
				"item": esc(r.item),
				"section": r.section,
				"score": cint(r.score),
				"percent": r.measure == "Percent",
				"comment": esc(r.comment),
			}
			for r in car.inspection
			if report and r.score
		],
		"inspection_note": esc(car.inspection_note) if report else "",
		"documents": [_(car.meta.get_label(d)) for d in DOCUMENTS if car.get(d)],
		"days": days,
		"similar": similar,
	}


@frappe.whitelist(allow_guest=True)
def get_cars(**args):
	frappe.local.lang = "fa"
	if not settings().enabled:
		return {"cars": [], "brands": [], "body_types": [], "count": 0}
	return list_cars(args)


@frappe.whitelist(allow_guest=True)
def simulate(vehicle: str, down_payment: float, months: int) -> dict:
	"""The instalments of a car for a down payment and a number of months, in rials, with the
	showroom's monthly rate: the same arithmetic as the sale contract."""
	frappe.local.lang = "fa"
	s = settings()
	car = public_car(vehicle)
	if not (s.show_prices and cint(car.website_show_price) and flt(car.asking_price)):
		frappe.throw(_("Ask an expert for the price of this car"))
	price = flt(car.asking_price)
	months = cint(months)
	if months not in s.months:
		frappe.throw(_("Choose one of the months offered"))
	down_payment = flt(down_payment)
	least = price * s.min_down_percent / 100
	if down_payment < least:
		frappe.throw(_("The down payment is at least {0}").format(price_text(least, s)))
	if down_payment >= price:
		return {
			"price": price,
			"down_payment": price,
			"financed": 0,
			"interest": 0,
			"total": price,
			"monthly": 0,
		}
	result = calculate(price, down_payment, 0, s.monthly_rate, months)
	return {
		"price": price,
		"down_payment": down_payment,
		"financed": result["financed"],
		"interest": result["interest"],
		"total": down_payment + result["total"],
		"monthly": result["rows"][0]["amount"],
		"last": result["rows"][-1]["amount"],
		"months": months,
		"monthly_rate": s.monthly_rate,
	}


def _check_rate(limit: int, by: str | None = None):
	"""At most `limit` requests an hour from one address, or for one `by` (a mobile number).
	(frappe.rate_limiter's decorator fails with a TypeError in this version of Frappe.)"""
	if not getattr(frappe.local, "request", None):
		return
	key = f"iran_showroom_requests:{by or frappe.local.request_ip or 'unknown'}"
	count = cint(frappe.cache.get_value(key)) + 1
	frappe.cache.set_value(key, count, expires_in_sec=60 * 60)
	if count > limit:
		frappe.throw(_("Too many requests were sent; please try again later"), frappe.RateLimitExceededError)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def send_inquiry(
	full_name: str,
	mobile: str,
	kind: str = "Call Me Back",
	vehicle: str | None = None,
	message: str | None = None,
	preferred_date: str | None = None,
	preferred_time: str | None = None,
	down_payment: float | None = None,
	months: int | None = None,
) -> dict:
	"""A customer's request from the website: it goes to the next expert in turn."""
	frappe.local.lang = "fa"
	# Per mobile number, and loosely per address: visitors behind one proxy (the showroom's own
	# website server, a shared office connection) share an address
	_check_rate(4, by=f"mobile:{normal_mobile(mobile)}")
	_check_rate(40)
	if kind not in ("Call Me Back", "Test Drive", "Instalment Plan", "Question"):
		kind = "Call Me Back"
	full_name = (full_name or "").strip()[:100]
	if len(full_name) < 2:
		frappe.throw(_("Write your name"))
	if vehicle:
		public_car(vehicle)
	if preferred_time not in ("Morning", "Afternoon", "Evening"):
		preferred_time = None
	if preferred_date:
		preferred_date = getdate(preferred_date)
		if preferred_date < getdate(nowdate()):
			preferred_date = None
	inquiry = frappe.get_doc(
		{
			"doctype": "Iran Car Inquiry",
			"kind": kind,
			"full_name": full_name,
			"mobile": normal_mobile(mobile),
			"vehicle": vehicle or None,
			"message": (message or "").strip()[:1000],
			"preferred_date": preferred_date,
			"preferred_time": preferred_time,
			"source": "Website",
		}
	)
	if vehicle and down_payment and months:
		plan = simulate(vehicle, down_payment, months)
		inquiry.update(
			{
				"sale_price": plan["price"],
				"down_payment": plan["down_payment"],
				"months": cint(months),
				"monthly_rate": plan.get("monthly_rate"),
				"monthly_amount": plan["monthly"],
			}
		)
	inquiry.insert(ignore_permissions=True)
	return {"name": inquiry.name}


# ---------------------------------------------------------------- the showroom's own website
# A website built separately (such as the React site of automodiran) reads the same cars as JSON.
# Same rules as the pages above: only what a buyer may see. Prices are in toman, text is plain
# (the site escapes it), photo addresses are relative to the ERP (/files/...).


def _mark_kind(condition) -> str:
	"""replaced, structure or painted: the three colours of the site's inspection map."""
	if "تعویض" in (condition.name or ""):
		return "replaced"
	return "structure" if condition.severity == "High" else "painted"


def _site_inspection(car) -> dict | None:
	if not cint(car.website_show_report) or not car.body_marks:
		return None
	from iran_erp.utils.jalali import format_jalali

	keys = dict(frappe.get_all("Iran Body Part", fields=["name", "diagram_key"], as_list=True))
	conditions = {
		c.name: c for c in frappe.get_all("Iran Body Condition", fields=["name", "severity", "color_code"])
	}
	panels, notes = [], []
	for row in car.body_marks:
		condition = conditions.get(row.condition) or frappe._dict(name=row.condition, severity="")
		status = row.condition or ""
		if not keys.get(row.body_part):
			# Chassis, pillars and the like are not on the map: they are written out
			notes.append(" ".join(filter(None, [f"{row.body_part}: {status}", row.description])))
			continue
		panels.append(
			{
				"number": len(panels) + 1,
				"name": row.body_part,
				"status": status,
				"kind": _mark_kind(condition),
				"key": keys[row.body_part],
				"description": row.description or "",
				"color": condition.get("color_code") or "",
			}
		)
	body_parts = frappe.db.count("Iran Body Part", {"disabled": 0, "diagram_key": ("is", "set")})
	return {
		"date": format_jalali(car.entry_date, "long") if car.entry_date else "",
		"summary": {
			"healthy": max(body_parts - len({p["key"] for p in panels}), 0),
			"withIssue": len(notes) + sum(1 for p in panels if p["kind"] == "structure"),
			"panelsWithHistory": len(panels),
		},
		"panels": panels,
		"structureNotes": notes,
		"note": car.inspection_note or "",
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_inventory() -> dict:
	"""Every car on the website with its model's specifications, in the shape the site uses."""
	frappe.local.lang = "fa"
	s = settings()
	if not s.enabled:
		return {"cars": [], "models": {}, "branches": []}
	names = frappe.get_all(
		"Iran Vehicle",
		filters={"show_on_website": 1, "status": ("in", PUBLIC)},
		pluck="name",
		order_by="featured desc, entry_date desc",
	)
	models, cars = {}, []
	for name in names:
		car = frappe.get_doc("Iran Vehicle", name)
		if car.car_model and car.car_model not in models:
			model = frappe.db.get_value(
				"Iran Car Model",
				car.car_model,
				["brand", "model", "title", "body_type", "engine", "model_3d"],
				as_dict=True,
			) or frappe._dict(model=car.car_model)
			models[car.car_model] = {
				"id": car.car_model,
				"name": model.title or car.car_model,
				"nameFa": " ".join(filter(None, [model.brand, model.model])) or car.car_model,
				"brand": model.brand or "",
				"bodyFa": _(model.body_type) if model.body_type else "",
				"engine": model.engine or "",
				"model3d": model.model_3d or "",
				"specs": [[r["label"], r["value"]] for r in spec_rows(car.car_model)],
				"features": spec_features(car.car_model),
			}
		show_price = bool(s.show_prices and cint(car.website_show_price) and flt(car.asking_price))
		year = (car.year or "").strip()
		cars.append(
			{
				"id": car.name,
				"carId": car.car_model or "",
				"trim": (models.get(car.car_model) or {}).get("engine", ""),
				"color": car.color or "",
				"branch": car.branch or "",
				"status": STATUS_LABEL.get(car.status, ""),
				"statusCode": car.status,
				# Toman whatever unit the showroom's own pages use; 0 when the price is not shown
				"price": round(flt(car.asking_price) / 10) if show_price else 0,
				"year": cint(year) if year.isdigit() else year,
				"yearLabel": to_persian_digits(year)
				+ (" میلادی" if car.made_in == "Imported Car" else " شمسی" if year else ""),
				"mileage": cint(car.mileage),
				"photos": [p.image for p in car.photos if p.image],
				"headline": car.website_headline or "",
				"description": car.website_description or "",
				"features": [line.strip() for line in (car.website_features or "").splitlines() if line.strip()],
				"featured": cint(car.featured),
				"documents": [_(car.meta.get_label(d)) for d in DOCUMENTS if car.get(d)],
				"inspection": _site_inspection(car),
			}
		)
	return {
		"showroom": {
			# settings() escapes for the HTML pages; the site escapes on its own
			"title": unescape(s.title),
			"phone": s.phone,
			"address": unescape(s.address),
			"monthlyRate": s.monthly_rate,
			"months": s.months,
			"minDownPercent": s.min_down_percent,
		},
		"branches": sorted({c["branch"] for c in cars if c["branch"]}),
		"models": models,
		"cars": cars,
	}
