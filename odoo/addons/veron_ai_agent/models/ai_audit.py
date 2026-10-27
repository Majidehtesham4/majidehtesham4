from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..services import redact


class AiAudit(models.Model):
	"""Every change of an agent's access and every action of an agent, kept as it happened: an event is
	never changed, and is removed only by the retention cleanup of an administrator"""

	_name = "veron.ai.audit"
	_description = "Agent Audit Event"
	_order = "id desc"

	date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
	event = fields.Char(required=True, readonly=True, index=True)
	agent_id = fields.Many2one("veron.ai.agent", readonly=True, index=True, ondelete="set null")
	run_id = fields.Many2one("veron.ai.run", readonly=True, index=True, ondelete="set null")
	user_id = fields.Many2one("res.users", "Person", readonly=True)
	company_id = fields.Many2one("res.company", readonly=True, index=True)
	tool_code = fields.Char("Tool", readonly=True)
	description = fields.Text(readonly=True)
	data_json = fields.Text("Data", readonly=True)

	@api.model
	def _log(self, event, agent=None, run=None, tool=None, description="", data=None):
		return self.sudo().create({
			"event": event, "agent_id": agent.id if agent else False, "run_id": run.id if run else False,
			"user_id": self.env.uid, "company_id": (run.company_id if run else agent.company_id if agent else self.env.company).id,
			"tool_code": tool or False, "description": redact.text(description, 2000),
			"data_json": redact.dumps(data, 8000) if data else False,
		})

	def write(self, vals):
		raise AccessError(_("An audit event is never changed."))

	def unlink(self):
		if not self.env.context.get("veron_ai_audit_purge") or not self.env.user.has_group("base.group_system"):
			raise AccessError(_("An audit event is removed only by the retention cleanup."))
		return super().unlink()
