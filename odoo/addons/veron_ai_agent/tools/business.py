"""Small analyses of sales, purchase, inventory, customers, products, the website, employees and tasks.
Each reads only through the agent's data scope and the person's rights; a tool whose module is not
installed is not offered."""

from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import fields
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from ..services.registry import Plan, Tool, ToolDenied, tool
from ..services.schema import strict_object
from .common import PERIOD, period, scoped

_lt = LazyTranslate(__name__)


def _span(ctx, args, default_days):
	start, end = period(ctx, args, default_days)
	return start, end, datetime.combine(start, time.min), datetime.combine(end, time.max)


class Analysis(Tool):
	category = "analyze"

	def plan(self, ctx, args):
		for model in self.models:
			ctx.check_model(model)
		return Plan(summary=self.label(ctx.env), model=self.models[0] if self.models else "")


@tool
class SalesSummary(Analysis):
	code = "sales_summary"
	name = _lt("Sales of a Period")
	description = _lt("Confirmed sales orders of a period: their number and amount, by day and by salesperson, and the biggest.")
	models = ("sale.order",)
	schema = strict_object(PERIOD)

	def execute(self, ctx, args, plan):
		start, end, dt_start, dt_end = _span(ctx, args, 1)
		model, domain = scoped(ctx, "sale.order", [("state", "=", "sale"), ("date_order", ">=", dt_start),
			("date_order", "<=", dt_end)])
		orders = model.search(domain)
		by_user = defaultdict(lambda: [0, 0.0])
		for order in orders:
			by_user[order.user_id.name or "-"][0] += 1
			by_user[order.user_id.name or "-"][1] += order.amount_untaxed
		top = orders.sorted("amount_untaxed", reverse=True)[:5]
		ctx.link(top)
		return {
			"period": f"{start} - {end}", "orders": len(orders), "untaxed": round(sum(orders.mapped("amount_untaxed")), 2),
			"total": round(sum(orders.mapped("amount_total")), 2),
			"by_salesperson": [{"salesperson": k, "orders": v[0], "untaxed": round(v[1], 2)} for k, v in by_user.items()],
			"biggest": [{"order": o.name, "customer": o.partner_id.display_name, "untaxed": o.amount_untaxed} for o in top],
		}


@tool
class QuotesPending(Analysis):
	code = "quotes_pending"
	name = _lt("Quotations to Follow Up")
	description = _lt("Quotations not confirmed, older than N days or past their validity, with the customer and the salesperson.")
	models = ("sale.order",)
	schema = strict_object({"older_than_days": {"type": "integer", "minimum": 0, "maximum": 365},
		"limit": {"type": "integer", "minimum": 1, "maximum": 100}})

	def execute(self, ctx, args, plan):
		limit_date = fields.Datetime.now() - timedelta(days=args.get("older_than_days", 3))
		today = fields.Date.context_today(ctx.env.user)
		model, domain = scoped(ctx, "sale.order", [("state", "in", ("draft", "sent"))])
		domain &= Domain("date_order", "<=", limit_date) | Domain("validity_date", "<", today)
		quotes = model.search(domain, limit=args.get("limit") or 30, order="date_order")
		ctx.link(quotes)
		return {"quotations": [{"id": q.id, "quotation": q.name, "customer": q.partner_id.display_name,
			"salesperson": q.user_id.name, "date": str(q.date_order.date()), "valid_until": str(q.validity_date or ""),
			"untaxed": q.amount_untaxed, "expired": bool(q.validity_date and q.validity_date < today)} for q in quotes]}


@tool
class CustomerSummary(Analysis):
	code = "customer_summary"
	name = _lt("Customer History")
	description = _lt("A customer's orders, open invoices, last activities and last messages, in short.")
	models = ("res.partner",)
	schema = strict_object({"partner_id": {"type": "integer", "minimum": 1}}, ["partner_id"])

	def execute(self, ctx, args, plan):
		partners, domain = scoped(ctx, "res.partner", [("id", "=", args["partner_id"])])
		partner = partners.search(domain, limit=1)
		if not partner:
			raise ToolDenied(ctx.env._("No such contact in the agent's data."))
		result = {"customer": partner.display_name, "city": partner.city, "phone": partner.phone, "email": partner.email}
		if "sale.order" in ctx.env and ctx.agent._scope("sale.order"):
			orders, order_domain = scoped(ctx, "sale.order", [("partner_id", "child_of", partner.commercial_partner_id.id)])
			sales = orders.search(order_domain, order="date_order desc", limit=10)
			result["orders"] = [{"order": o.name, "date": str(o.date_order.date()), "state": o.state, "total": o.amount_total}
				for o in sales]
		if "account.move" in ctx.env and ctx.agent._scope("account.move"):
			moves, move_domain = scoped(ctx, "account.move", [("partner_id", "child_of", partner.commercial_partner_id.id),
				("move_type", "=", "out_invoice"), ("state", "=", "posted"), ("payment_state", "in", ("not_paid", "partial"))])
			open_invoices = moves.search(move_domain)
			result["open_invoices"] = len(open_invoices)
			result["open_amount"] = round(sum(open_invoices.mapped("amount_residual")), 2)
		messages = ctx.env["mail.message"].search([("model", "=", "res.partner"), ("res_id", "=", partner.id),
			("message_type", "in", ("comment", "email"))], limit=5, order="id desc")
		result["last_messages"] = [{"date": str(m.date), "by": m.author_id.name} for m in messages]
		ctx.link(partner)
		return result


@tool
class PurchaseSummary(Analysis):
	code = "purchase_summary"
	name = _lt("Purchases of a Period")
	description = _lt("Confirmed purchase orders of a period: their number and amount, by vendor.")
	models = ("purchase.order",)
	schema = strict_object(PERIOD)

	def execute(self, ctx, args, plan):
		start, end, dt_start, dt_end = _span(ctx, args, 7)
		model, domain = scoped(ctx, "purchase.order", [("state", "in", ("purchase", "done")),
			("date_approve", ">=", dt_start), ("date_approve", "<=", dt_end)])
		orders = model.search(domain)
		by_vendor = defaultdict(float)
		for order in orders:
			by_vendor[order.partner_id.display_name] += order.amount_untaxed
		return {"period": f"{start} - {end}", "orders": len(orders),
			"untaxed": round(sum(orders.mapped("amount_untaxed")), 2),
			"by_vendor": sorted(({"vendor": k, "untaxed": round(v, 2)} for k, v in by_vendor.items()),
				key=lambda r: -r["untaxed"])[:15]}


@tool
class PurchaseLate(Analysis):
	code = "purchase_late"
	name = _lt("Late Purchase Deliveries")
	description = _lt("Purchase order lines past their planned date and not fully received, by vendor.")
	models = ("purchase.order.line",)
	schema = strict_object({"limit": {"type": "integer", "minimum": 1, "maximum": 100}})

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, "purchase.order.line", [("order_id.state", "=", "purchase"),
			("date_planned", "<", fields.Datetime.now())])
		lines = model.search(domain, limit=500).filtered(lambda l: l.qty_received < l.product_qty)
		lines = lines[:args.get("limit") or 50]
		ctx.link(lines.order_id)
		today = fields.Datetime.now()
		return {"late_lines": [{"order": l.order_id.name, "vendor": l.partner_id.display_name,
			"product": l.product_id.display_name, "ordered": l.product_qty, "received": l.qty_received,
			"planned": str(l.date_planned.date()), "days_late": (today - l.date_planned).days} for l in lines]}


@tool
class PurchaseCompare(Analysis):
	code = "purchase_compare"
	name = _lt("Compare Purchase Offers")
	description = _lt("For a product: the prices of open requests for quotation and of the vendors' price lists, cheapest first.")
	models = ("purchase.order.line",)
	schema = strict_object({"product_id": {"type": "integer", "minimum": 1}}, ["product_id"])

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, "purchase.order.line", [("product_id", "=", args["product_id"]),
			("order_id.state", "in", ("draft", "sent", "to approve"))])
		offers = [{"source": l.order_id.name, "vendor": l.partner_id.display_name, "unit_price": l.price_unit,
			"currency": l.currency_id.name, "quantity": l.product_qty, "date": str(l.date_planned.date() if l.date_planned else "")}
			for l in model.search(domain, limit=50)]
		if "product.supplierinfo" in ctx.env and ctx.agent._scope("product.supplierinfo"):
			infos, info_domain = scoped(ctx, "product.supplierinfo", [("product_tmpl_id.product_variant_ids", "in", [args["product_id"]])])
			offers += [{"source": ctx.env._("Price list"), "vendor": i.partner_id.display_name, "unit_price": i.price,
				"currency": i.currency_id.name, "quantity": i.min_qty, "date": str(i.date_end or "")} for i in infos.search(info_domain)]
		return {"offers": sorted(offers, key=lambda o: o["unit_price"]),
			"note": "Compare the same unit and currency; prices of other sources are checked by a person."}


@tool
class OrderReceiptBillCheck(Analysis):
	code = "order_receipt_bill_check"
	name = _lt("Order, Receipt and Bill Differences")
	description = _lt("Purchase lines whose billed quantity differs from the received one, or billed at another price.")
	models = ("purchase.order.line",)
	schema = strict_object({"limit": {"type": "integer", "minimum": 1, "maximum": 200}})

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, "purchase.order.line", [("order_id.state", "in", ("purchase", "done")),
			("qty_invoiced", ">", 0)])
		issues = []
		for line in model.search(domain, limit=1000):
			if "invoice_lines" not in line._fields:
				break
			reasons = []
			if line.qty_invoiced > line.qty_received + 1e-6:
				reasons.append(ctx.env._("billed %(billed)s, received %(received)s", billed=line.qty_invoiced, received=line.qty_received))
			for bill_line in line.invoice_lines.filtered(lambda b: b.parent_state == "posted"):
				if abs(bill_line.price_unit - line.price_unit) > 0.01 * max(line.price_unit, 1):
					reasons.append(ctx.env._("billed at %(bill)s, ordered at %(order)s", bill=bill_line.price_unit, order=line.price_unit))
			if reasons:
				issues.append({"order": line.order_id.name, "vendor": line.partner_id.display_name,
					"product": line.product_id.display_name, "differences": reasons})
			if len(issues) >= (args.get("limit") or 50):
				break
		return {"differences": issues, "note": "Differences are for a person to check, not errors by anyone."}


@tool
class StockAlerts(Analysis):
	code = "stock_alerts"
	name = _lt("Stock Shortages and Slow Stock")
	description = _lt("Products under their reordering minimum or below zero, and products in stock with no movement for N days.")
	models = ("stock.quant",)
	schema = strict_object({"slow_days": {"type": "integer", "minimum": 7, "maximum": 730},
		"limit": {"type": "integer", "minimum": 1, "maximum": 100}})

	def execute(self, ctx, args, plan):
		limit = args.get("limit") or 30
		result = {}
		quants, quant_domain = scoped(ctx, "stock.quant", [("location_id.usage", "=", "internal")])
		negative = quants.search(quant_domain & Domain("quantity", "<", 0), limit=limit)
		result["below_zero"] = [{"product": q.product_id.display_name, "location": q.location_id.display_name,
			"quantity": q.quantity} for q in negative]
		if "stock.warehouse.orderpoint" in ctx.env and ctx.agent._scope("stock.warehouse.orderpoint"):
			points, point_domain = scoped(ctx, "stock.warehouse.orderpoint")
			short = points.search(point_domain, limit=500).filtered(lambda p: p.qty_forecast < p.product_min_qty)[:limit]
			result["under_minimum"] = [{"product": p.product_id.display_name, "warehouse": p.warehouse_id.name,
				"forecast": p.qty_forecast, "minimum": p.product_min_qty} for p in short]
		if "stock.move" in ctx.env and ctx.agent._scope("stock.move"):
			since = fields.Datetime.now() - timedelta(days=args.get("slow_days") or 90)
			moves, move_domain = scoped(ctx, "stock.move", [("state", "=", "done"), ("date", ">=", since)])
			moved = set(moves.search(move_domain).mapped("product_id").ids)
			stocked = quants.search(quant_domain & Domain("quantity", ">", 0), limit=2000)
			slow = defaultdict(float)
			for quant in stocked:
				if quant.product_id.id not in moved:
					slow[quant.product_id.display_name] += quant.quantity
			result["no_movement"] = [{"product": k, "quantity": v} for k, v in list(slow.items())[:limit]]
		return result


@tool
class StockTransferSuggest(Analysis):
	code = "stock_transfer_suggest"
	name = _lt("Suggest Transfers Between Warehouses")
	description = _lt("Suggests moving a product from a warehouse with more than its maximum to one under its minimum. "
		"Only suggestions are made; nothing is moved.")
	category = "suggest"
	action = "suggest"
	models = ("stock.warehouse.orderpoint",)
	schema = strict_object({"limit": {"type": "integer", "minimum": 1, "maximum": 50}})

	def execute(self, ctx, args, plan):
		points, domain = scoped(ctx, "stock.warehouse.orderpoint")
		by_product = defaultdict(list)
		for point in points.search(domain, limit=1000):
			by_product[point.product_id].append(point)
		suggestions = []
		for product, product_points in by_product.items():
			short = [p for p in product_points if p.qty_forecast < p.product_min_qty]
			extra = [p for p in product_points if p.product_max_qty and p.qty_forecast > p.product_max_qty]
			for need in short:
				for give in extra:
					if give.warehouse_id == need.warehouse_id:
						continue
					quantity = min(need.product_min_qty - need.qty_forecast, give.qty_forecast - give.product_max_qty)
					if quantity > 0:
						suggestions.append({"product": product.display_name, "product_id": product.id,
							"from_warehouse": give.warehouse_id.name, "to_warehouse": need.warehouse_id.name, "quantity": quantity})
			if len(suggestions) >= (args.get("limit") or 20):
				break
		return {"suggestions": suggestions, "note": "Suggestions only; a person decides and makes the transfer."}


@tool
class ProductQuality(Analysis):
	code = "product_quality"
	name = _lt("Product Information Check")
	description = _lt("Products sold whose information is incomplete: no description, no photo, no barcode, a zero price, and "
		"on the website no description or search-engine title.")
	models = ("product.template",)
	schema = strict_object({"limit": {"type": "integer", "minimum": 1, "maximum": 200}})

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, "product.template", [("sale_ok", "=", True)])
		checks = [("description_sale", ctx.env._("no sales description")), ("image_128", ctx.env._("no photo")),
			("barcode", ctx.env._("no barcode")), ("list_price", ctx.env._("price is zero"))]
		web = [("website_description", ctx.env._("no website description")), ("website_meta_title", ctx.env._("no search-engine title")),
			("website_meta_description", ctx.env._("no search-engine description"))]
		products = model.search(domain, limit=1000)
		issues = []
		for product in products:
			missing = [label for name, label in checks if name in product._fields and not product[name]]
			if "is_published" in product._fields and product.is_published:
				missing += [label for name, label in web if name in product._fields and not product[name]]
			if missing:
				issues.append({"id": product.id, "product": product.display_name, "missing": missing})
			if len(issues) >= (args.get("limit") or 50):
				break
		return {"checked": len(products), "incomplete": issues}


@tool
class WebsiteReport(Analysis):
	code = "website_report"
	name = _lt("Website Visits, Orders and Ratings")
	description = _lt("Visits and visitors of the website, its orders and the ratings of products in a period.")
	models = ("website.visitor",)
	schema = strict_object(PERIOD)

	def execute(self, ctx, args, plan):
		start, end, dt_start, dt_end = _span(ctx, args, 7)
		result = {"period": f"{start} - {end}"}
		visitors, visitor_domain = scoped(ctx, "website.visitor", [("last_connection_datetime", ">=", dt_start)])
		result["visitors"] = visitors.search_count(visitor_domain)
		if "website.track" in ctx.env and ctx.agent._scope("website.track"):
			tracks, track_domain = scoped(ctx, "website.track", [("visit_datetime", ">=", dt_start), ("visit_datetime", "<=", dt_end)])
			result["page_views"] = tracks.search_count(track_domain)
			rows = tracks._read_group(track_domain, ["url"], ["__count"], limit=10, order="__count desc")
			result["top_pages"] = [{"url": url, "views": count} for url, count in rows]
		if "sale.order" in ctx.env and "website_id" in ctx.env["sale.order"]._fields and ctx.agent._scope("sale.order"):
			orders, order_domain = scoped(ctx, "sale.order", [("website_id", "!=", False), ("state", "=", "sale"),
				("date_order", ">=", dt_start), ("date_order", "<=", dt_end)])
			found = orders.search(order_domain)
			result["website_orders"] = len(found)
			result["website_sales"] = round(sum(found.mapped("amount_untaxed")), 2)
		if "rating.rating" in ctx.env and ctx.agent._scope("rating.rating"):
			ratings, rating_domain = scoped(ctx, "rating.rating", [("create_date", ">=", dt_start), ("rating", ">", 0)])
			found = ratings.search(rating_domain, limit=500)
			result["ratings"] = len(found)
			result["average_rating"] = round(sum(found.mapped("rating")) / len(found), 2) if found else None
		return result


@tool
class EmployeeMissingInfo(Analysis):
	code = "employee_missing_info"
	name = _lt("Employees' Missing Information")
	description = _lt("Employees whose file lacks information: contact, identity number, bank account, emergency contact, contract.")
	models = ("hr.employee",)
	schema = strict_object({"limit": {"type": "integer", "minimum": 1, "maximum": 200}})

	FIELDS = ["work_email", "mobile_phone", "identification_id", "birthday", "bank_account_id", "emergency_contact",
		"emergency_phone", "contract_date_start", "wage"]

	def execute(self, ctx, args, plan):
		model, domain = scoped(ctx, "hr.employee")
		readable = set(ctx.fields("hr.employee"))
		checked = [name for name in self.FIELDS if name in model._fields and name in readable]
		labels = {name: model._fields[name].get_description(ctx.env)["string"] for name in checked}
		issues = []
		for employee in model.search(domain, limit=2000):
			missing = [labels[name] for name in checked if not employee[name]]
			if missing:
				issues.append({"id": employee.id, "employee": employee.name, "department": employee.department_id.name,
					"missing": missing})
			if len(issues) >= (args.get("limit") or 100):
				break
		return {"checked_fields": list(labels.values()), "employees": issues,
			"note": "Fields the agent may not read are not checked." if len(checked) < len(self.FIELDS) else ""}


@tool
class AttendanceLeaveReview(Analysis):
	code = "attendance_leave_review"
	name = _lt("Time Off and Long Days to Review")
	description = _lt("Time off waiting for approval, and attendances longer than N hours in a period, for a person to review.")
	models = ("hr.leave",)
	schema = strict_object(dict(PERIOD, long_hours={"type": "number", "minimum": 4, "maximum": 24}))

	def execute(self, ctx, args, plan):
		start, end, dt_start, dt_end = _span(ctx, args, 7)
		leaves, leave_domain = scoped(ctx, "hr.leave", [("state", "in", ("confirm", "validate1"))])
		result = {"period": f"{start} - {end}", "leaves_waiting": [{"employee": l.employee_id.name,
			"type": l.holiday_status_id.name, "from": str(l.request_date_from), "to": str(l.request_date_to),
			"days": l.number_of_days} for l in leaves.search(leave_domain, limit=100)]}
		if "hr.attendance" in ctx.env and ctx.agent._scope("hr.attendance"):
			attendances, att_domain = scoped(ctx, "hr.attendance", [("check_in", ">=", dt_start), ("check_in", "<=", dt_end),
				("worked_hours", ">", args.get("long_hours") or 10)])
			result["long_days"] = [{"employee": a.employee_id.name, "date": str(a.check_in.date()),
				"hours": round(a.worked_hours, 2)} for a in attendances.search(att_domain, limit=100)]
		return result


@tool
class TasksFollowup(Analysis):
	code = "tasks_followup"
	name = _lt("Overdue Tasks and Requests")
	description = _lt("Overdue activities and project tasks, by person, for follow-up.")
	models = ("mail.activity",)
	schema = strict_object({"limit": {"type": "integer", "minimum": 1, "maximum": 200}})

	def execute(self, ctx, args, plan):
		today = fields.Date.context_today(ctx.env.user)
		activities, act_domain = scoped(ctx, "mail.activity", [("date_deadline", "<", today)])
		found = activities.search(act_domain, limit=args.get("limit") or 100, order="date_deadline")
		by_user = defaultdict(int)
		for activity in found:
			by_user[activity.user_id.name or "-"] += 1
		result = {"overdue_activities": [{"summary": a.summary or a.activity_type_id.name, "on": a.res_name,
			"for": a.user_id.name, "deadline": str(a.date_deadline)} for a in found[:50]],
			"by_person": [{"person": k, "overdue": v} for k, v in sorted(by_user.items(), key=lambda i: -i[1])]}
		if "project.task" in ctx.env and ctx.agent._scope("project.task"):
			tasks, task_domain = scoped(ctx, "project.task", [("date_deadline", "<", fields.Datetime.now()),
				("is_closed", "=", False)])
			result["overdue_tasks"] = [{"task": t.name, "project": t.project_id.name, "assigned": t.user_ids.mapped("name"),
				"deadline": str(t.date_deadline.date())} for t in tasks.search(task_domain, limit=50)]
		return result


@tool
class UnitsStatus(Analysis):
	code = "units_status"
	name = _lt("Status of the Departments")
	description = _lt("For each department: employees, overdue activities of its people, and time off waiting.")
	models = ("hr.department",)
	schema = strict_object({})

	def execute(self, ctx, args, plan):
		departments, domain = scoped(ctx, "hr.department")
		today = fields.Date.context_today(ctx.env.user)
		result = []
		for department in departments.search(domain, limit=100):
			users = department.member_ids.user_id
			row = {"department": department.name, "employees": len(department.member_ids)}
			if users and ctx.agent._scope("mail.activity"):
				activities, act_domain = scoped(ctx, "mail.activity", [("user_id", "in", users.ids), ("date_deadline", "<", today)])
				row["overdue_activities"] = activities.search_count(act_domain)
			if "hr.leave" in ctx.env and ctx.agent._scope("hr.leave"):
				leaves, leave_domain = scoped(ctx, "hr.leave", [("department_id", "=", department.id), ("state", "=", "confirm")])
				row["time_off_waiting"] = leaves.search_count(leave_domain)
			result.append(row)
		return {"departments": result}
