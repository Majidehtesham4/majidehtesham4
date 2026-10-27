"""Working with people and other agents: asking the responsible person, reporting to the set destinations,
follow-up activities, contacting someone outside (sensitive: approved by a person), and the supervisor's
tasks and reviews"""

from datetime import timedelta

from markupsafe import Markup, escape

from odoo import fields
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from ..services.registry import Plan, Tool, ToolDenied, tool
from ..services.schema import strict_object

_lt = LazyTranslate(__name__)


@tool
class RequestHumanInput(Tool):
	code = "request_human_input"
	name = _lt("Ask the Responsible Person")
	description = _lt("Asks the agent's responsible person a question, for information, a document or a decision that is "
		"missing. The run waits for the answer; use it instead of guessing.")
	category = "human"
	schema = strict_object({"question": {"type": "string", "minLength": 3, "maxLength": 2000}}, ["question"])

	def plan(self, ctx, args):
		return Plan(summary=args["question"][:200])

	def execute(self, ctx, args, plan):
		request = ctx.run._ask(args["question"])
		return {"status": "needs_info", "request": request.name, "asked": request.approver_user_ids.mapped("name")}


@tool
class NotifyInternal(Tool):
	code = "notify_internal"
	name = _lt("Report to the Set Destinations")
	description = _lt("Sends a report to the people and the channel set on the agent, inside Odoo. It cannot choose other recipients.")
	category = "notify"
	schema = strict_object({
		"subject": {"type": "string", "maxLength": 200},
		"body": {"type": "string", "minLength": 1, "maxLength": 20000},
	}, ["body"])

	def plan(self, ctx, args):
		if not (ctx.agent.notify_user_ids or ctx.agent.notify_channel_id):
			raise ToolDenied(ctx.env._("The agent has no report destinations set."))
		return Plan(summary=args.get("subject") or ctx.env._("Report"))

	def execute(self, ctx, args, plan):
		from ..models.ai_run import markdown_html

		agent = ctx.agent
		body = Markup("<p><b>%s</b></p>%s") % (args.get("subject") or agent.name, markdown_html(args["body"]))
		if agent.notify_user_ids:
			ctx.run.sudo().message_notify(body=body, subject=args.get("subject") or agent.name,
				partner_ids=agent.notify_user_ids.partner_id.ids, email_layout_xmlid="mail.mail_notification_light")
		if agent.notify_channel_id:
			agent.notify_channel_id.sudo().message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_comment")
		return {"sent_to": agent.notify_user_ids.mapped("name") + agent.notify_channel_id.mapped("name")}


@tool
class NotifyExternal(Tool):
	code = "notify_external"
	name = _lt("Message Someone Outside")
	description = _lt("Sends an email or an SMS to a contact (a customer, a vendor). Contacting someone outside always waits "
		"for a person's approval unless a manager set an explicit rule.")
	category = "external"
	action = "execute"
	risk = "high"
	sensitive = "external_contact"
	models = ("res.partner",)
	schema = strict_object({
		"partner_id": {"type": "integer", "minimum": 1},
		"channel": {"type": "string", "enum": ["email", "sms"]},
		"subject": {"type": "string", "maxLength": 200},
		"body": {"type": "string", "minLength": 1, "maxLength": 5000},
	}, ["partner_id", "channel", "body"])

	def _partner(self, ctx, args):
		ctx.check_model("res.partner")
		partner = ctx.env["res.partner"].search(ctx.domain("res.partner") & Domain("id", "=", args["partner_id"]), limit=1)
		if not partner:
			raise ToolDenied(ctx.env._("No such contact in the agent's data."))
		return partner

	def plan(self, ctx, args):
		partner = self._partner(ctx, args)
		if args["channel"] == "email" and not partner.email:
			raise ToolDenied(ctx.env._("%s has no email.", partner.name))
		if args["channel"] == "sms" and "sms.sms" not in ctx.env:
			raise ToolDenied(ctx.env._("SMS is not installed."))
		return Plan(summary=ctx.env._("%(channel)s to %(partner)s: %(body)s", channel=args["channel"], partner=partner.name,
			body=args["body"][:300]), model="res.partner", res_ids=partner.ids, company_ids=ctx.companies(partner))

	def execute(self, ctx, args, plan):
		partner = self._partner(ctx, args)
		if args["channel"] == "sms":
			partner._message_sms(args["body"], partner_ids=partner.ids)
		else:
			partner.message_post(body=Markup("<p>%s</p>") % args["body"], subject=args.get("subject") or ctx.agent.name,
				partner_ids=partner.ids, message_type="comment", subtype_xmlid="mail.mt_comment")
		ctx.link(partner)
		return {"sent": args["channel"], "to": partner.display_name}


@tool
class ActivityCreate(Tool):
	code = "activity_create"
	name = _lt("Create a Follow-up Activity")
	description = _lt("Creates a to-do activity on a record in the agent's data, for an internal user, with a deadline.")
	category = "draft"
	action = "draft"
	schema = strict_object({
		"model": {"type": "string", "maxLength": 64},
		"id": {"type": "integer", "minimum": 1},
		"user_id": {"type": "integer", "minimum": 1, "description": "The internal user it is for; the agent's responsible by default"},
		"summary": {"type": "string", "minLength": 2, "maxLength": 200},
		"note": {"type": "string", "maxLength": 2000},
		"days": {"type": "integer", "minimum": 0, "maximum": 90},
	}, ["model", "id", "summary"])

	def _record(self, ctx, args):
		ctx.check_model(args["model"])
		record = ctx.env[args["model"]].search(ctx.domain(args["model"]) & Domain("id", "=", args["id"]), limit=1)
		if not record or "activity_ids" not in record._fields:
			raise ToolDenied(ctx.env._("No such record, or it has no activities."))
		return record

	def plan(self, ctx, args):
		record = self._record(ctx, args)
		return Plan(summary=ctx.env._("Activity on %(record)s: %(summary)s", record=record.display_name, summary=args["summary"]),
			model=args["model"], res_ids=record.ids, company_ids=ctx.companies(record))

	def execute(self, ctx, args, plan):
		record = self._record(ctx, args)
		user = ctx.env["res.users"].browse(args.get("user_id") or ctx.agent.responsible_user_id.id).exists()
		if not user or user.share or not (user.company_ids & ctx.env.companies):
			raise ToolDenied(ctx.env._("The activity is only for an internal user of these companies."))
		activity = record.activity_schedule("mail.mail_activity_data_todo", user_id=user.id, summary=args["summary"],
			note=escape(args.get("note") or ""), date_deadline=fields.Date.context_today(record) + timedelta(days=args.get("days") or 0))
		ctx.link(record)
		return {"activity": activity.id, "on": record.display_name, "for": user.name}


@tool
class DelegateTask(Tool):
	code = "delegate_task"
	name = _lt("Give a Task to an Agent")
	description = _lt("Supervisor only: gives a task to one of the agents it may delegate to, optionally after other tasks. "
		"A ready task runs at once with the same rights; its result comes back for review.")
	category = "coordinate"
	supervisor_only = True
	schema = strict_object({
		"agent": {"type": "string", "maxLength": 120, "description": "The name of the agent, from the delegates"},
		"title": {"type": "string", "minLength": 2, "maxLength": 200},
		"instructions": {"type": "string", "minLength": 2, "maxLength": 4000},
		"after_task_ids": {"type": "array", "maxItems": 10, "items": {"type": "integer", "minimum": 1}},
	}, ["agent", "title", "instructions"])

	def plan(self, ctx, args):
		agent = ctx.agent.delegate_agent_ids.filtered(lambda a: a.name == args["agent"])[:1]
		if not agent:
			names = ", ".join(ctx.agent.delegate_agent_ids.mapped("name")) or "-"
			raise ToolDenied(ctx.env._("%(agent)s is not a delegate of this supervisor. Delegates: %(names)s", agent=args["agent"],
				names=names))
		return Plan(summary=ctx.env._("Task for %(agent)s: %(title)s", agent=agent.name, title=args["title"]),
			data={"agent_id": agent.id})

	def execute(self, ctx, args, plan):
		Task = ctx.env["veron.ai.task"].sudo()
		after = Task.browse(args.get("after_task_ids") or []).exists().filtered(lambda t: t.parent_run_id == ctx.run)
		task = Task._delegate(ctx.run.sudo(), ctx.env["veron.ai.agent"].sudo().browse(plan.data["agent_id"]), args["title"],
			args["instructions"], after)
		task._start()
		result = {"task_id": task.id, "state": task.state}
		if task.result_run_id:
			run = task.result_run_id
			result.update({"run": run.name, "run_state": run.state, "result": (run.output_html and
				str(run.output_html)[:6000]) or "", "findings": run.finding_ids.mapped("message")[:20]})
		return result


@tool
class ReviewTask(Tool):
	code = "review_task"
	name = _lt("Review a Task Result")
	description = _lt("Supervisor only: records whether a task's result is accepted in the AI review, not accepted, or sent "
		"to a person, and why. Acceptance here is not an accounting or legal approval.")
	category = "coordinate"
	supervisor_only = True
	schema = strict_object({
		"task_id": {"type": "integer", "minimum": 1},
		"decision": {"type": "string", "enum": ["accepted", "rejected", "escalated"]},
		"reason": {"type": "string", "minLength": 5, "maxLength": 3000},
	}, ["task_id", "decision", "reason"])

	def _task(self, ctx, args):
		task = ctx.env["veron.ai.task"].sudo().browse(args["task_id"]).exists()
		if not task or task.parent_run_id != ctx.run.sudo():
			raise ToolDenied(ctx.env._("The task is not one of this run's tasks."))
		return task

	def plan(self, ctx, args):
		task = self._task(ctx, args)
		return Plan(summary=ctx.env._("Review of %(task)s: %(decision)s", task=task.name, decision=args["decision"]))

	def execute(self, ctx, args, plan):
		task = self._task(ctx, args)
		task._review(args["decision"], args["reason"])
		return {"task": task.name, "review": task.review}


@tool
class EscalateToHuman(Tool):
	code = "escalate_to_human"
	name = _lt("Stop and Refer to a Person")
	description = _lt("On an error, a doubt or something unclear: stops here and refers the matter to the supervising person.")
	category = "human"
	schema = strict_object({"reason": {"type": "string", "minLength": 5, "maxLength": 3000}}, ["reason"])

	def plan(self, ctx, args):
		return Plan(summary=args["reason"][:200])

	def execute(self, ctx, args, plan):
		ctx.finding(args["reason"], kind="info", severity="critical")
		user = ctx.agent.supervisor_user_id or ctx.agent.responsible_user_id
		ctx.run.sudo().activity_schedule("mail.mail_activity_data_todo", user_id=user.id,
			summary=ctx.env._("Referred by %s", ctx.agent.name), note=escape(args["reason"]))
		return {"referred_to": user.name, "stop": True}
