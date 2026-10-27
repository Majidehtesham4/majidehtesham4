"""The petty cash closing, step by step, for an agent. Each tool does one step with the rights of the person
the run is for; posting is a separate, sensitive tool that always waits for a person's approval (unless a
manager sets an explicit rule), and runs with the rights of whoever approves it."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

from odoo.addons.veron_ai_agent.services.providers import ProviderError
from odoo.addons.veron_ai_agent.services.registry import Plan, Tool, ToolDenied, ToolNeedsInfo, tool
from odoo.addons.veron_ai_agent.services.schema import strict_object
from odoo.addons.veron_ai_agent.tools.common import scoped
from odoo.addons.veron_core.models import jalali

_lt = LazyTranslate(__name__)

MODULE = "veron_ai_agent_account"
CLOSING = {"closing_id": {"type": "integer", "minimum": 1}}
# The kind of a finding of the run, from the kind of the receipt's finding
FINDING_KINDS = {"duplicate_file": "duplicate", "duplicate_image": "duplicate", "duplicate_number": "duplicate",
	"duplicate_amount": "duplicate", "amount": "missing", "date": "policy", "limit": "limit", "category": "policy",
	"tax_id": "missing", "reading": "unusual"}


def _closing(ctx, closing_id):
	model, domain = scoped(ctx, "veron.petty.cash.closing", [("id", "=", closing_id)])
	closing = model.search(domain, limit=1)
	if not closing:
		raise ToolDenied(ctx.env._("No such petty cash closing in the agent's data."))
	return closing


def _receipts(closing):
	return [{"receipt": r.name, "id": r.id, "vendor": r.vendor_name or r.partner_id.name or None, "date": str(r.date or ""),
		"amount": r.amount, "state": r.state, "findings": r.issue_ids.filtered(lambda i: not i.resolved).mapped("message")}
		for r in closing.receipt_ids]


def _last_month_end(today):
	year, month, _day = jalali.to_jalali(today)
	year, month = (year, month - 1) if month > 1 else (year - 1, 12)
	return jalali.to_gregorian(year, month, jalali.month_length(year, month))


class PettyCashTool(Tool):
	module = MODULE
	models = ("veron.petty.cash.closing",)


@tool
class PettyCashOpen(PettyCashTool):
	code = "petty_cash_open"
	name = _lt("Petty Cash: Open the Closing and Ask for Documents")
	description = _lt("For each petty cash fund the agent may see: the open closing, or a new one up to the end of the "
		"last Shamsi month (or the date given); the custodian is asked for the receipts. Returns where each fund stands.")
	category = "draft"
	action = "draft"
	models = ("veron.petty.cash.fund", "veron.petty.cash.closing")
	schema = strict_object({"fund_id": {"type": "integer", "minimum": 1},
		"date_to": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD; the end of the last Shamsi month by default"}})

	def _funds(self, ctx, args):
		model, domain = scoped(ctx, "veron.petty.cash.fund", [("id", "=", args["fund_id"])] if args.get("fund_id") else [])
		funds = model.search(domain)
		if args.get("fund_id") and not funds:
			raise ToolDenied(ctx.env._("No such fund in the agent's data."))
		return funds

	def plan(self, ctx, args):
		ctx.check_model("veron.petty.cash.closing")
		funds = self._funds(ctx, args)
		return Plan(summary=ctx.env._("Petty cash: closings of %s", ", ".join(funds.mapped("name")) or "-"),
			model="veron.petty.cash.closing", company_ids=ctx.companies(funds))

	def execute(self, ctx, args, plan):
		today = fields.Date.context_today(ctx.env.user)
		Closing = ctx.env["veron.petty.cash.closing"]
		result = []
		for fund in self._funds(ctx, args):
			closing = fund.closing_ids.filtered(lambda c: c.state in ("draft", "review", "to_approve"))[:1]
			created = False
			if not closing:
				start = fund._next_start()
				try:
					end = fields.Date.to_date(args["date_to"]) if args.get("date_to") else _last_month_end(today)
				except ValueError as error:
					raise ToolDenied(ctx.env._("Dates are written YYYY-MM-DD.")) from error
				if end < start:
					end = today - timedelta(days=1) if today > start else today
				closing = Closing.create({"fund_id": fund.id, "date_from": start, "date_to": end})
				created = True
			if closing.state == "draft" and not closing.requested_at:
				closing._request_documents()
			ctx.link(closing)
			result.append({"fund": fund.name, "custodian": fund.custodian_user_id.name, "closing_id": closing.id,
				"closing": closing.name, "period": closing.period, "state": closing.state, "new": created,
				"documents_asked": bool(closing.requested_at), "receipts": len(closing.receipt_ids),
				"waiting_custodian_confirmation": len(closing.receipt_ids.filtered(lambda r: r.state in ("new", "extracted")))})
		return {"funds": result}


@tool
class PettyCashReview(PettyCashTool):
	code = "petty_cash_review"
	name = _lt("Petty Cash: Read and Check the Receipts")
	description = _lt("Adds files of this run as receipts of a closing, reads the unread receipts into fields for the "
		"custodian to confirm, and checks the confirmed ones for duplicates and against the fund's policy. Each "
		"finding is for a person to review; a receipt without findings is accepted in the AI review only.")
	category = "draft"
	action = "draft"
	schema = strict_object({**CLOSING, "add_file_ids": {"type": "array", "maxItems": 50,
		"items": {"type": "integer", "minimum": 1}, "description": "Files of this run to add as receipts"}}, ["closing_id"])

	def plan(self, ctx, args):
		closing = _closing(ctx, args["closing_id"])
		if closing.state not in ("draft", "review"):
			raise ToolDenied(ctx.env._("%s is past its review.", closing.name))
		return Plan(summary=ctx.env._("Check the receipts of %s", closing.name), model="veron.petty.cash.closing",
			res_ids=closing.ids, company_ids=ctx.companies(closing))

	def execute(self, ctx, args, plan):
		closing = _closing(ctx, args["closing_id"])
		Receipt = ctx.env["veron.petty.cash.receipt"]
		added = []
		ids = args.get("add_file_ids") or []
		for source in ctx.sources(ids) if ids else []:
			if source.kind not in ("image", "pdf"):
				continue
			if Receipt.search_count([("closing_id", "=", closing.id), ("source_id", "=", source.id)]):
				continue
			added.append(Receipt.create({"closing_id": closing.id, "source_id": source.id}).name)
		read, unread = [], []
		provider = ctx.provider("vision")
		for receipt in closing.receipt_ids.filtered(lambda r: r.state == "new" and r.source_id):
			try:
				values = receipt._extract(provider)
			except ProviderError as error:
				unread.append({"receipt": receipt.name, "reason": error.text(ctx.env)})
				continue
			if values is None:
				unread.append({"receipt": receipt.name, "reason": "No reading provider; the custodian enters the fields."})
			else:
				read.append(receipt.name)
		waiting = closing.receipt_ids.filtered(lambda r: r.state in ("new", "extracted"))
		checked = {"accepted": [], "review": []}
		if closing.state == "review":
			outcome = closing._review()
			checked = {key: [r.name for r in outcome[key]] for key in ("accepted", "review")}
			for receipt in closing.receipt_ids.filtered(lambda r: r.state == "review"):
				for issue in receipt.issue_ids.filtered(lambda i: not i.resolved):
					ctx.finding(f"{receipt.name}: {issue.message}", kind=FINDING_KINDS.get(issue.kind, "info"),
						severity="critical" if issue.severity == "critical" else "warning", record=receipt)
		elif waiting and read:
			closing.activity_schedule("mail.mail_activity_data_todo", user_id=closing.custodian_user_id.id,
				summary=ctx.env._("Confirm the receipts read for %s", closing.name),
				note=ctx.env._("Check what was read from each receipt against its file and confirm it."))
		ctx.link(closing)
		return {"closing": closing.name, "state": closing.state, "added": added, "read": read, "not_read": unread,
			"waiting_custodian_confirmation": waiting.mapped("name"), "accepted_in_ai_review": checked["accepted"],
			"needs_person_review": checked["review"], "receipts": _receipts(closing),
			"note": "Accepted in the AI review is not an accounting approval." if closing.state == "review" else
			"The checks run after the custodian gives the documents."}


@tool
class PettyCashDraftEntry(PettyCashTool):
	code = "petty_cash_draft_entry"
	name = _lt("Petty Cash: Make the Draft Settlement Entry")
	description = _lt("Makes the draft entry of a reviewed closing from its accepted receipts: each expense on its "
		"account, against the petty cash account of the custodian. Nothing is posted.")
	category = "draft"
	action = "draft"
	models = ("veron.petty.cash.closing", "account.move")
	schema = strict_object(CLOSING, ["closing_id"])

	def plan(self, ctx, args):
		closing = _closing(ctx, args["closing_id"])
		return Plan(summary=ctx.env._("Draft entry of %(closing)s: %(amount)s", closing=closing.name,
			amount=f"{closing.accepted_amount:,.0f}"), amount=closing.accepted_amount, model="veron.petty.cash.closing",
			res_ids=closing.ids, company_ids=ctx.companies(closing))

	def execute(self, ctx, args, plan):
		closing = _closing(ctx, args["closing_id"])
		pending = closing.receipt_ids.filtered(lambda r: r.state not in ("accepted", "rejected"))
		if closing.state == "review" and pending:
			raise ToolNeedsInfo(ctx.env._("Receipts of %(closing)s wait for your review: %(receipts)s. Accept or reject "
				"each in Petty Cash, then answer here.", closing=closing.name, receipts=", ".join(pending.mapped("name"))))
		try:
			move = closing._draft_move()
		except UserError as error:
			raise ToolDenied(str(error)) from error
		ctx.link(move)
		ctx.link(closing)
		return {"closing": closing.name, "draft_entry": move.name or move.display_name, "draft_id": move.id,
			"amount": closing.accepted_amount, "posted": False,
			"next": "Posting waits for the approval of a person with the right to post."}


@tool
class PettyCashPost(PettyCashTool):
	code = "petty_cash_post"
	name = _lt("Petty Cash: Post the Settlement Entry")
	description = _lt("Posts the checked draft entry of a closing. Posting always waits for a person's approval, and is "
		"done with the rights of the person who approves it.")
	category = "execute"
	action = "execute"
	risk = "high"
	sensitive = "post"
	models = ("veron.petty.cash.closing", "account.move")
	schema = strict_object(CLOSING, ["closing_id"])

	def plan(self, ctx, args):
		closing = _closing(ctx, args["closing_id"])
		if closing.state != "to_approve" or not closing.move_id:
			raise ToolDenied(ctx.env._("%s has no draft entry to post.", closing.name))
		return Plan(summary=ctx.env._("Post the settlement entry of %(closing)s (%(fund)s, %(period)s): %(amount)s",
			closing=closing.name, fund=closing.fund_id.name, period=closing.period, amount=f"{closing.accepted_amount:,.0f}"),
			amount=closing.accepted_amount, model="veron.petty.cash.closing", res_ids=closing.ids,
			company_ids=ctx.companies(closing))

	def execute(self, ctx, args, plan):
		closing = _closing(ctx, args["closing_id"])
		try:
			move = closing._post()
		except UserError as error:
			raise ToolDenied(str(error)) from error
		return {"closing": closing.name, "entry": move.name, "posted": True, "by": ctx.env.user.name}


@tool
class PettyCashReport(PettyCashTool):
	code = "petty_cash_report"
	name = _lt("Petty Cash: Settlement Report")
	description = _lt("The settlement of a closing: opening balance, money given in the period, receipts given, accepted, "
		"not accepted and to review, and the closing balance; the PDF is kept on the closing.")
	category = "report"
	schema = strict_object({**CLOSING, "pdf": {"type": "boolean"}}, ["closing_id"])

	def plan(self, ctx, args):
		closing = _closing(ctx, args["closing_id"])
		return Plan(summary=ctx.env._("Settlement report of %s", closing.name), model="veron.petty.cash.closing",
			res_ids=closing.ids, company_ids=ctx.companies(closing))

	def execute(self, ctx, args, plan):
		closing = _closing(ctx, args["closing_id"])
		figures = closing._figures()
		if args.get("pdf", True):
			figures["pdf"] = closing._make_report().name
		figures["receipts_list"] = _receipts(closing)
		ctx.link(closing)
		return figures
