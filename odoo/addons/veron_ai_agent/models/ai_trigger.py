"""When an agent runs by itself, as in Odoo's AI app: on a schedule, on a date of the records, after a record is
made, or after a field of it changes. The last three are automated actions of Odoo that queue a run of the agent
for the record; the run is done by the queue of the runs, with the rights of the agent's run-as user."""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

KINDS = [("schedule", "On a Schedule"), ("date", "Based on a Date Field"), ("create", "After Creation"),
	("update", "After Update")]
# The runs one firing may queue, and how long a record waits before the same trigger runs for it again
MAX_RECORDS = 20
QUIET_MINUTES = 5


class AiTrigger(models.Model):
	_name = "veron.ai.trigger"
	_description = "AI Agent Trigger"
	_order = "agent_id, id"

	name = fields.Char(compute="_compute_name")
	agent_id = fields.Many2one("veron.ai.agent", required=True, ondelete="cascade", index=True)
	kind = fields.Selection(KINDS, required=True, default="create")
	active = fields.Boolean(default=True)
	model_id = fields.Many2one("ir.model", "Records", ondelete="cascade",
		domain=[("transient", "=", False), ("model", "not like", "veron.ai.%")])
	model = fields.Char(related="model_id.model")
	date_field_id = fields.Many2one("ir.model.fields", "Date Field", ondelete="cascade",
		domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime'))]")
	delay = fields.Integer(default=0)
	delay_mode = fields.Selection([("after", "After"), ("before", "Before")], default="after")
	delay_unit = fields.Selection([("minutes", "Minutes"), ("hour", "Hours"), ("day", "Days"), ("month", "Months")],
		default="day")
	field_ids = fields.Many2many("ir.model.fields", string="When These Fields Change",
		domain="[('model_id', '=', model_id), ('store', '=', True)]")
	filter_domain = fields.Char("Only the Records", default="[]")
	input_text = fields.Text("Request", required=True, help="What the agent is asked each time, about the record")
	schedule_id = fields.Many2one("veron.ai.schedule", readonly=True, ondelete="set null")
	automation_id = fields.Many2one("base.automation", readonly=True, ondelete="set null", copy=False)
	fired_count = fields.Integer(readonly=True)
	last_fired = fields.Datetime(readonly=True)

	@api.depends("kind", "model_id", "date_field_id", "agent_id")
	def _compute_name(self):
		labels = dict(self._fields["kind"]._description_selection(self.env))
		for trigger in self:
			parts = [labels.get(trigger.kind, "")]
			if trigger.model_id:
				parts.append(trigger.model_id.name)
			if trigger.date_field_id:
				parts.append(trigger.date_field_id.field_description)
			trigger.name = " · ".join(filter(None, parts))

	@api.constrains("kind", "model_id", "date_field_id")
	def _check(self):
		for trigger in self:
			if trigger.kind != "schedule" and not trigger.model_id:
				raise ValidationError(_("Say which records start the agent."))
			if trigger.kind == "date" and not trigger.date_field_id:
				raise ValidationError(_("Say which date of the records starts the agent."))

	@api.model_create_multi
	def create(self, vals_list):
		triggers = super().create(vals_list)
		triggers._sync()
		return triggers

	def write(self, vals):
		result = super().write(vals)
		if not self.env.context.get("veron_ai_trigger_sync"):
			self._sync()
		return result

	def unlink(self):
		self.automation_id.sudo().unlink()
		self.schedule_id.sudo().unlink()
		return super().unlink()

	def _sync(self):
		"""The automated action, or the schedule, of each trigger, as it says"""
		for trigger in self.sudo().with_context(veron_ai_trigger_sync=True):
			if trigger.kind == "schedule":
				trigger.automation_id.unlink()
				values = {"agent_id": trigger.agent_id.id, "input_text": trigger.input_text, "active": trigger.active,
					"name": trigger.input_text[:60]}
				if trigger.schedule_id:
					trigger.schedule_id.write(values)
				else:
					trigger.schedule_id = self.env["veron.ai.schedule"].create(values)
				if trigger.active and not trigger.agent_id.trigger_schedule:
					trigger.agent_id.trigger_schedule = True
				continue
			trigger.schedule_id.unlink()
			values = {
				"name": _("AI: %(agent)s · %(trigger)s", agent=trigger.agent_id.name, trigger=trigger.name),
				"model_id": trigger.model_id.id, "active": trigger.active and trigger.agent_id.enabled,
				"filter_domain": trigger.filter_domain or "[]",
				"trigger": {"date": "on_time", "create": "on_create", "update": "on_write"}[trigger.kind],
			}
			if trigger.kind == "date":
				values.update({"trg_date_id": trigger.date_field_id.id, "trg_date_range": trigger.delay,
					"trg_date_range_mode": trigger.delay_mode, "trg_date_range_type": trigger.delay_unit})
			if trigger.kind == "update":
				values["trigger_field_ids"] = [(6, 0, trigger.field_ids.ids)]
			code = f"env['veron.ai.trigger'].sudo().browse({trigger.id})._fire(records)"
			if trigger.automation_id:
				trigger.automation_id.write(values)
				trigger.automation_id.action_server_ids.write({"code": code, "model_id": trigger.model_id.id})
			else:
				values["action_server_ids"] = [(0, 0, {"name": values["name"], "state": "code", "code": code,
					"model_id": trigger.model_id.id, "usage": "base_automation"})]
				trigger.automation_id = self.env["base.automation"].create(values)

	def _fire(self, records):
		"""Runs of the agent queued for the records; not for those of a run of the same agent, nor twice in a row"""
		self.ensure_one()
		agent = self.agent_id
		if not self.active or not agent.enabled or not records:
			return self.env["veron.ai.run"]
		Run = self.env["veron.ai.run"].sudo()
		current = self.env.context.get("veron_ai_run_id")
		if current and Run.browse(current).agent_id == agent:
			return Run
		since = fields.Datetime.now() - timedelta(minutes=QUIET_MINUTES)
		user = agent.run_as_user_id or agent.responsible_user_id
		runs = Run
		for record in records[:MAX_RECORDS]:
			marker = f"[{record._name},{record.id}]"
			if Run.search_count([("agent_id", "=", agent.id), ("create_date", ">=", since),
					("input_text", "ilike", marker)]):
				continue
			text = _("%(request)s\n\nThe record: %(kind)s «%(name)s» %(marker)s", request=self.input_text,
				kind=record._description, name=record.display_name, marker=marker)
			runs |= Run._enqueue(agent, user, initiator="event", text=text, record=record)
		if runs:
			self.sudo().with_context(veron_ai_trigger_sync=True).write({"fired_count": self.fired_count + len(runs),
				"last_fired": fields.Datetime.now()})
		return runs

	def action_open_schedule(self):
		self.ensure_one()
		if not self.schedule_id:
			raise UserError(_("This trigger has no schedule."))
		return {"type": "ir.actions.act_window", "res_model": "veron.ai.schedule", "res_id": self.schedule_id.id,
			"view_mode": "form", "target": "new"}


class AiAgentTriggers(models.Model):
	_inherit = "veron.ai.agent"

	trigger_ids = fields.One2many("veron.ai.trigger", "agent_id", "Triggers")

	def write(self, vals):
		result = super().write(vals)
		if "enabled" in vals:
			# The automated actions of an agent that is off do not run
			self.trigger_ids.filtered(lambda t: t.kind != "schedule")._sync()
		return result
