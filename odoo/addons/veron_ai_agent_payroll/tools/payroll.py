"""Payroll for an agent. Every amount comes from the payroll engine and the confirmed rates of the year;
an agent gives no amount, rate or rule, and stops to ask when the year's rates are not confirmed. Salary
amounts are kept out of what the tools return, so they are not sent to the language model: the tools
return names, counts, flags and percentages. Nothing here pays anyone."""

from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.veron_ai_agent.services.registry import Plan, Tool, ToolDenied, ToolNeedsInfo, tool
from odoo.addons.veron_ai_agent.services.schema import strict_object
from odoo.addons.veron_ai_agent.tools.common import scoped
from odoo.addons.veron_core.models import jalali

MODULE = "veron_ai_agent_payroll"
MONTH = {"type": "string", "maxLength": 7, "description": "Shamsi year/month, e.g. 1405/07; this month by default"}


def _month(ctx, args):
	"""(year, month, first day, last day) of the Shamsi month asked, or of today"""
	if args.get("month"):
		try:
			year, month = (int(p) for p in args["month"].replace("-", "/").split("/"))
			start = jalali.to_gregorian(year, month, 1)
		except (ValueError, TypeError) as error:
			raise ToolDenied(ctx.env._("The month is written as 1405/07.")) from error
	else:
		from odoo import fields

		year, month, _day = jalali.to_jalali(fields.Date.context_today(ctx.env.user))
		start = jalali.to_gregorian(year, month, 1)
	return year, month, start, jalali.to_gregorian(year, month, jalali.month_length(year, month))


def _label(year, month):
	return f"{jalali.MONTHS[month - 1]} {year}"


def _rates(ctx, year):
	"""The year's rates, confirmed by a person; otherwise the run stops and asks"""
	rates = ctx.env["veron.payroll.year"].sudo().search([("year", "=", year), ("company_id", "=", ctx.env.company.id)], limit=1)
	if not rates:
		raise ToolNeedsInfo(ctx.env._("The payroll rates of %s are not entered. Enter them from the official resolution in "
			"Payroll, Configuration, Yearly Rates, confirm them, then answer here.", year))
	if rates.state != "confirmed":
		raise ToolNeedsInfo(ctx.env._("The payroll rates of %s are not confirmed. Check them against the official resolution "
			"in Payroll, Configuration, Yearly Rates and confirm them; the agent does not guess rates.", year))
	return rates


def _employees(ctx, start, end, ids=None):
	extra = [("contract_date_start", "<=", end), "|", ("contract_date_end", "=", False), ("contract_date_end", ">=", start)]
	if ids:
		extra.append(("id", "in", ids))
	model, domain = scoped(ctx, "hr.employee", extra)
	return model.search(domain)


def _payslips(ctx, start, end, extra=None):
	model, domain = scoped(ctx, "hr.payslip", [("date_from", "=", start), ("date_to", "=", end)] + (extra or []))
	return model.search(domain)


def _line(payslip, code):
	return sum(payslip.line_ids.filtered(lambda line: line.code == code).mapped("total"))


class PayrollTool(Tool):
	module = MODULE
	models = ("hr.payslip", "hr.employee")

	def plan(self, ctx, args):
		for model in self.models:
			ctx.check_model(model)
		year, month, _start, _end = _month(ctx, args)
		return Plan(summary=f"{self.name}: {_label(year, month)}", model="hr.payslip", company_ids=[ctx.env.company.id])


@tool
class PayrollInputsCheck(PayrollTool):
	code = "payroll_inputs_check"
	name = "Payroll: Check the Inputs"
	description = ("Before the payslips of a Shamsi month: the year's rates confirmed, and for each employee with a "
		"contract in the month, the structure, the wage against the minimum, the national code, the insurance number "
		"and the bank account. Returns what is missing; no amount.")
	category = "read"
	schema = strict_object({"month": MONTH})

	def execute(self, ctx, args, plan):
		year, month, start, end = _month(ctx, args)
		rates = _rates(ctx, year)
		missing = []
		employees = _employees(ctx, start, end)
		for employee in employees:
			version = employee.version_id
			problems = []
			if not version.struct_id:
				problems.append("no salary structure")
			if not version.wage:
				problems.append("no wage")
			elif version.wage < rates.min_monthly:
				problems.append("wage below the minimum of the year")
			if not employee.identification_id:
				problems.append("no national code")
			if version.veron_insured and not version.veron_insurance_number:
				problems.append("no insurance number")
			if "primary_bank_account_id" in employee._fields and not employee.primary_bank_account_id:
				problems.append("no bank account")
			if problems:
				missing.append({"employee": employee.name, "missing": problems})
		existing = _payslips(ctx, start, end)
		return {"month": _label(year, month), "rates": f"{year} confirmed", "employees": len(employees),
			"ready": len(employees) - len(missing), "to_complete": missing,
			"payslips": {state: len(existing.filtered(lambda p, s=state: p.state == s)) for state in ("draft", "verify", "done")}}


@tool
class PayslipDraftsCompute(PayrollTool):
	code = "payslip_drafts_compute"
	name = "Payroll: Compute the Payslips"
	description = ("Makes the draft payslips of a Shamsi month for the employees with a contract (or those given) and "
		"computes them with the payroll engine and the confirmed rates; draft and waiting payslips are computed again, "
		"done payslips are left as they are. Nothing is confirmed or paid. Returns counts and problems, no amount.")
	category = "draft"
	action = "draft"
	schema = strict_object({"month": MONTH, "employee_ids": {"type": "array", "maxItems": 500,
		"items": {"type": "integer", "minimum": 1}}})

	def execute(self, ctx, args, plan):
		year, month, start, end = _month(ctx, args)
		_rates(ctx, year)
		Payslip = ctx.env["hr.payslip"]
		computed, failed, kept = [], [], 0
		for employee in _employees(ctx, start, end, args.get("employee_ids")):
			payslip = _payslips(ctx, start, end, [("employee_id", "=", employee.id), ("state", "!=", "cancel")])[:1]
			# Draft and waiting payslips are computed again; a done one is left as it is
			if payslip and payslip.state not in ("draft", "verify"):
				kept += 1
				continue
			try:
				with ctx.env.cr.savepoint():
					if not payslip:
						payslip = Payslip.create({"employee_id": employee.id, "date_from": start, "date_to": end})
						payslip.onchange_employee()
						payslip.write({"date_from": start, "date_to": end})
					payslip.compute_sheet()
			except UserError as error:
				failed.append({"employee": employee.name, "reason": str(error)[:300]})
				continue
			computed.append(payslip)
		ctx.link(Payslip.browse([p.id for p in computed])[:30])
		return {"month": _label(year, month), "computed": len(computed), "left_as_they_are": kept, "problems": failed,
			"next": "A payroll manager checks and confirms the payslips; paying them is done in accounting."}


@tool
class PayrollComparePrevious(PayrollTool):
	code = "payroll_compare_previous"
	name = "Payroll: Changes From Last Month"
	description = ("Compares each payslip of a Shamsi month with the same employee's payslip of the month before: the "
		"change of gross and net in percent, above a threshold, and who is new or missing. No amount.")
	category = "analyze"
	schema = strict_object({"month": MONTH, "threshold": {"type": "number", "minimum": 1, "maximum": 100,
		"description": "Percent of change shown; 15 by default"}})

	def execute(self, ctx, args, plan):
		year, month, start, end = _month(ctx, args)
		previous_year, previous_month = (year, month - 1) if month > 1 else (year - 1, 12)
		p_start = jalali.to_gregorian(previous_year, previous_month, 1)
		p_end = jalali.to_gregorian(previous_year, previous_month, jalali.month_length(previous_year, previous_month))
		threshold = args.get("threshold") or 15
		current = _payslips(ctx, start, end, [("state", "!=", "cancel")])
		before = {p.employee_id: p for p in _payslips(ctx, p_start, p_end, [("state", "!=", "cancel")])}
		changes, new = [], []
		for payslip in current:
			old = before.pop(payslip.employee_id, None)
			if not old:
				new.append(payslip.employee_id.name)
				continue
			row = {"employee": payslip.employee_id.name}
			for code in ("GROSS", "NET"):
				was, now = _line(old, code), _line(payslip, code)
				if was:
					row[f"{code.lower()}_change_percent"] = round((now - was) / abs(was) * 100, 1)
			if any(abs(v) >= threshold for k, v in row.items() if k.endswith("_percent")):
				changes.append(row)
		return {"month": _label(year, month), "compared_with": _label(previous_year, previous_month),
			"threshold_percent": threshold, "changes": changes, "new_this_month": new,
			"missing_this_month": [employee.name for employee in before],
			"note": "A change is something to check (overtime, absence, a new rate), not an error by itself."}


@tool
class PayslipPdfPrepare(PayrollTool):
	code = "payslip_pdf_prepare"
	name = "Payroll: Prepare the Payslip PDFs"
	description = ("Prepares the PDF of each computed payslip of a Shamsi month. Each PDF opens only for its employee "
		"(in My Payslips) and payroll managers. It sends nothing outside.")
	category = "report"
	schema = strict_object({"month": MONTH, "notify": {"type": "boolean",
		"description": "Tell each employee with a user inside Odoo that the payslip is ready"}})

	def execute(self, ctx, args, plan):
		year, month, start, end = _month(ctx, args)
		payslips = _payslips(ctx, start, end, [("state", "in", ("draft", "verify", "done"))]).filtered("line_ids")
		Document = ctx.env["veron.payslip.document"]
		documents = Document.browse()
		for payslip in payslips:
			documents |= Document._prepare(payslip, _label(year, month))
		notified = 0
		if args.get("notify"):
			for document in documents.filtered("user_id"):
				document.sudo().payslip_id.message_notify(partner_ids=document.user_id.partner_id.ids,
					subject=ctx.env._("Your payslip of %s", document.month),
					body=ctx.env._("Your payslip of %s is ready in Employees, My Payslips.", document.month))
				notified += 1
		return {"month": _label(year, month), "prepared": len(documents), "employees_told": notified,
			"without_user": [d.employee_id.name for d in documents if not d.user_id],
			"note": "Only the employee and payroll managers open each PDF."}
