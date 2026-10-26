"""Campaigns run by a scheduled job: the records matching a campaign's filter join it, each step is
scheduled after its delay, done when due if its condition still holds, then the next steps follow."""

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

UNITS = [("hours", "Hours"), ("days", "Days"), ("weeks", "Weeks"), ("months", "Months")]


class Campaign(models.Model):
	_name = "veron.automation.campaign"
	_description = "Marketing Campaign"
	_inherit = ["mail.thread"]

	name = fields.Char(required=True, tracking=True)
	model_id = fields.Many2one("ir.model", "Applies To", required=True, ondelete="cascade",
		domain="[('is_mail_thread', '=', True), ('transient', '=', False)]",
		default=lambda self: self.env.ref("base.model_res_partner", raise_if_not_found=False))
	model_name = fields.Char(related="model_id.model", store=True)
	domain = fields.Char("Filter", default="[]", help="Which records take part")
	state = fields.Selection([("draft", "Draft"), ("running", "Running"), ("stopped", "Stopped")], default="draft", required=True, tracking=True)
	activity_ids = fields.One2many("veron.automation.activity", "campaign_id", "Steps", copy=True)
	participant_ids = fields.One2many("veron.automation.participant", "campaign_id")
	participant_count = fields.Integer(compute="_compute_counts")
	running_count = fields.Integer(compute="_compute_counts")
	company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

	def _compute_counts(self):
		for campaign in self:
			campaign.participant_count = len(campaign.participant_ids)
			campaign.running_count = len(campaign.participant_ids.filtered(lambda p: p.state == "running"))

	def action_start(self):
		for campaign in self:
			if not campaign.activity_ids:
				raise UserError(_("Add the steps of the campaign first."))
		self.write({"state": "running"})
		self._run()

	def action_stop(self):
		self.write({"state": "stopped"})
		self.participant_ids.trace_ids.filtered(lambda t: t.state == "scheduled").write({"state": "canceled"})

	def action_draft(self):
		self.write({"state": "draft"})

	def action_participants(self):
		self.ensure_one()
		return {
			"type": "ir.actions.act_window",
			"name": _("Participants"),
			"res_model": "veron.automation.participant",
			"view_mode": "list,form",
			"domain": [("campaign_id", "=", self.id)],
		}

	def _records(self):
		self.ensure_one()
		return self.env[self.model_name].search(safe_eval(self.domain or "[]"))

	def _sync(self):
		"""The records matching the filter that have not joined yet: join, with the first steps scheduled"""
		now = fields.Datetime.now()
		for campaign in self:
			joined = set(campaign.participant_ids.mapped("res_id"))
			new = [rid for rid in campaign._records().ids if rid not in joined]
			roots = campaign.activity_ids.filtered(lambda a: not a.parent_id)
			for rid in new[:1000]:
				self.env["veron.automation.participant"].create({
					"campaign_id": campaign.id,
					"res_id": rid,
					"trace_ids": [(0, 0, {"activity_id": a.id, "schedule_date": a._after(now)}) for a in roots],
				})

	def _run(self):
		self.filtered(lambda c: c.state == "running")._sync()
		traces = self.env["veron.automation.trace"].search([
			("campaign_id", "in", self.ids), ("campaign_id.state", "=", "running"),
			("state", "=", "scheduled"), ("schedule_date", "<=", fields.Datetime.now()),
		], order="schedule_date, id", limit=500)
		for trace in traces:
			trace._execute()
		self.participant_ids.filtered(lambda p: p.state == "running" and not p.trace_ids.filtered(lambda t: t.state == "scheduled")).write({"state": "done"})

	@api.model
	def _cron_run(self):
		self.search([("state", "=", "running")])._run()


class CampaignActivity(models.Model):
	_name = "veron.automation.activity"
	_description = "Campaign Step"
	_order = "sequence, id"

	campaign_id = fields.Many2one("veron.automation.campaign", required=True, ondelete="cascade")
	model_name = fields.Char(related="campaign_id.model_name")
	sequence = fields.Integer(default=10)
	name = fields.Char(required=True)
	parent_id = fields.Many2one("veron.automation.activity", "After Step", ondelete="cascade",
		domain="[('campaign_id', '=', campaign_id), ('id', '!=', id)]",
		help="Empty: counted from when the record joins the campaign")
	delay_count = fields.Integer("Delay", default=0)
	delay_unit = fields.Selection(UNITS, default="days", required=True)
	kind = fields.Selection([("email", "Email"), ("sms", "SMS"), ("todo", "To-Do"), ("action", "Action")], required=True, default="email")
	mail_template_id = fields.Many2one("mail.template", "Email Template", domain="[('model', '=', model_name)]")
	sms_body = fields.Text("SMS Text", help="Placeholders like {{ object.name }} are replaced for each record")
	todo_summary = fields.Char("To-Do")
	todo_user_id = fields.Many2one("res.users", "To-Do For", help="Empty: the record's salesperson, or the campaign's creator")
	server_action_id = fields.Many2one("ir.actions.server", "Action", domain="[('model_id.model', '=', model_name)]")
	domain = fields.Char("Condition", default="[]", help="The step is done only for the records matching this, at that time")
	trace_ids = fields.One2many("veron.automation.trace", "activity_id")
	done_count = fields.Integer("Done", compute="_compute_counts")
	error_count = fields.Integer("Errors", compute="_compute_counts")
	scheduled_count = fields.Integer("Waiting", compute="_compute_counts")

	def _compute_counts(self):
		for activity in self:
			states = activity.trace_ids.mapped("state")
			activity.done_count = states.count("processed")
			activity.error_count = states.count("error")
			activity.scheduled_count = states.count("scheduled")

	def _after(self, moment):
		return moment + relativedelta(**{self.delay_unit: self.delay_count})

	def _run_on(self, record):
		"""The step done for one record"""
		if self.kind == "email":
			if not self.mail_template_id:
				raise UserError(_("No email template."))
			self.mail_template_id.send_mail(record.id)
		elif self.kind == "sms":
			body = self.env["mail.render.mixin"]._render_template(
				self.sms_body or "", record._name, record.ids, engine="inline_template")[record.id]
			number = next((record[f] for f in ("mobile", "phone", "phone_sanitized") if f in record and record[f]), None)
			if not number and "partner_id" in record and record.partner_id:
				number = record.partner_id.phone
			if not number:
				raise UserError(_("No phone number."))
			self.env["sms.sms"].sudo().create({"number": number, "body": body})
		elif self.kind == "todo":
			user = self.todo_user_id or ("user_id" in record and record.user_id) or self.campaign_id.create_uid
			record.activity_schedule("mail.mail_activity_data_todo", summary=self.todo_summary or self.name, user_id=user.id)
		elif self.kind == "action":
			if not self.server_action_id:
				raise UserError(_("No action."))
			self.server_action_id.with_context(active_model=record._name, active_id=record.id, active_ids=record.ids).run()


class Participant(models.Model):
	_name = "veron.automation.participant"
	_description = "Campaign Participant"
	_order = "id desc"

	campaign_id = fields.Many2one("veron.automation.campaign", required=True, ondelete="cascade", index=True)
	res_id = fields.Integer("Record ID", required=True, index=True)
	record_name = fields.Char("Record", compute="_compute_record_name")
	state = fields.Selection([("running", "Running"), ("done", "Done")], default="running", required=True)
	trace_ids = fields.One2many("veron.automation.trace", "participant_id")

	_unique_record = models.Constraint("unique(campaign_id, res_id)", "A record takes part in a campaign once.")

	def _compute_record_name(self):
		for participant in self:
			record = self.env[participant.campaign_id.model_name].browse(participant.res_id).exists()
			participant.record_name = record.display_name if record else _("(deleted)")


class Trace(models.Model):
	_name = "veron.automation.trace"
	_description = "Campaign Step Done"
	_order = "schedule_date desc, id desc"

	participant_id = fields.Many2one("veron.automation.participant", required=True, ondelete="cascade", index=True)
	campaign_id = fields.Many2one(related="participant_id.campaign_id", store=True, index=True)
	activity_id = fields.Many2one("veron.automation.activity", "Step", required=True, ondelete="cascade")
	record_name = fields.Char(related="participant_id.record_name")
	schedule_date = fields.Datetime("Scheduled On", required=True, index=True)
	done_date = fields.Datetime("Done On")
	state = fields.Selection([("scheduled", "Waiting"), ("processed", "Done"), ("skipped", "Condition not met"),
		("canceled", "Canceled"), ("error", "Error")], default="scheduled", required=True, index=True)
	message = fields.Char()

	def _execute(self):
		self.ensure_one()
		activity = self.activity_id
		record = self.env[activity.campaign_id.model_name].browse(self.participant_id.res_id).exists()
		if not record:
			self.write({"state": "canceled", "message": _("The record was deleted.")})
			return
		condition = safe_eval(activity.domain or "[]")
		if condition and not record.filtered_domain(condition):
			self.write({"state": "skipped", "done_date": fields.Datetime.now()})
			return
		try:
			with self.env.cr.savepoint():
				activity._run_on(record)
		except Exception as error:  # noqa: BLE001 - one record's error must not stop the campaign
			_logger.info("Campaign step %s on %s failed: %s", activity.name, record, error)
			self.write({"state": "error", "message": str(error)[:250], "done_date": fields.Datetime.now()})
			return
		now = fields.Datetime.now()
		self.write({"state": "processed", "done_date": now})
		children = activity.campaign_id.activity_ids.filtered(lambda a: a.parent_id == activity)
		self.create([{"participant_id": self.participant_id.id, "activity_id": child.id, "schedule_date": child._after(now)}
			for child in children])
