"""Guides of the AI sections, written out in full: each says what the section is for and how to use it step by
step, with what the program has today (the commands of the library, the tools, the teams) listed from its data.
They need no AI to read."""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import registry


class AiGuide(models.Model):
	_name = "veron.ai.guide"
	_description = "Guide of an AI Section"
	_order = "sequence, id"

	code = fields.Char(required=True, index=True)
	name = fields.Char(required=True)
	sequence = fields.Integer(default=10)
	icon = fields.Char(default="fa-book")
	summary = fields.Char()
	body = fields.Html(sanitize_attributes=False)
	action_ref = fields.Char("Section", help="The action of the section the guide is about, to open it from the guide")
	details = fields.Html("What the Program Has Now", compute="_compute_details", sanitize=False)

	_code_unique = models.Constraint("unique(code)", "One guide per section.")

	def _compute_details(self):
		for guide in self:
			method = getattr(guide, f"_details_{guide.code}", None)
			guide.details = method() if method else False

	# --- what the program has now, written from its data

	def _grid(self, head, rows):
		cells = Markup("").join(Markup("<th>%s</th>") % h for h in head)
		body = Markup("").join(Markup("<tr>%s</tr>") % Markup("").join(Markup("<td>%s</td>") % (c or "") for c in row)
			for row in rows)
		return Markup("<table class='table table-sm table-bordered'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>") % (
			cells, body)

	def _details_library(self):
		Intent = self.env["veron.ai.intent"].sudo()
		sections = dict(Intent._fields["section"]._description_selection(self.env))
		rows = []
		for intent in Intent.search([], order="section, sequence, id"):
			if not intent._usable(self.env.user):
				continue
			phrases = [line for line in (intent.phrases or "").splitlines() if line.strip()][:3]
			asked = "، ".join(slot.get("question", "").split("؟")[0] + "؟" for slot in intent._slots()
				if slot.get("required") and slot.get("question")) or "-"
			rows.append((sections.get(intent.section, intent.section), intent.name, intent.example or (phrases[:1] or [""])[0],
				" / ".join(phrases), asked))
		if not rows:
			return Markup("<p>%s</p>") % _("No command of the library is open to you.")
		return Markup("<h4>%s</h4>") % _("The commands open to you now") + self._grid(
			[_("Section"), _("Command"), _("Example"), _("Other ways to say it"), _("It asks you")], rows)

	def _details_tools(self):
		levels = dict(self.env["veron.ai.agent"]._fields["authority_level"]._description_selection(self.env))
		rows = []
		for tool in self.env["veron.ai.tool"].sudo().search([], order="level, name"):
			spec = registry.get(tool.code)
			if not spec or not spec.available(self.env):
				continue
			rows.append((tool.name, levels.get(str(tool.level), tool.level), _("Yes") if tool.sensitive else "",
				tool.models_used or "", tool.description or ""))
		return Markup("<h4>%s</h4>") % _("The tools of this program") + self._grid(
			[_("Tool"), _("Needs at least"), _("Sensitive"), _("Works on"), _("What it does")], rows)

	def _details_team(self):
		supervisors = self.env["veron.ai.agent"].search([("is_supervisor", "=", True)])
		if not supervisors:
			return Markup("<p>%s</p>") % _("No team is made yet. Build one from AI Agents, Agents, Build a Team.")
		parts = [Markup("<h4>%s</h4>") % _("The teams of this program")]
		for supervisor in supervisors:
			members = supervisor.delegate_agent_ids
			state = _("on") if supervisor.enabled else _("off")
			parts.append(Markup("<p><b>%s</b> (%s) - %s</p>") % (supervisor.name, state, _("its parts:")))
			parts.append(Markup("<ul>%s</ul>") % Markup("").join(
				Markup("<li>%s%s</li>") % (member.name, "" if member.enabled else Markup(" <i>(%s)</i>") % _("off"))
				for member in members))
		return Markup("").join(parts)

	def _details_agents(self):
		agents = self.env["veron.ai.agent"].search([])
		rows = [(agent.name, agent.template_id.name or _("Assistant"), agent.supervisor_agent_id.name or "",
			dict(agent._fields["authority_level"]._description_selection(self.env)).get(agent.authority_level),
			_("on") if agent.enabled else _("off")) for agent in agents]
		if not rows:
			return False
		return Markup("<h4>%s</h4>") % _("The agents of this program") + self._grid(
			[_("Name"), _("Role"), _("In the team of"), _("Authority"), _("State")], rows)

	# --- opening

	def action_open_section(self):
		self.ensure_one()
		if not self.action_ref:
			raise UserError(_("This guide has no section to open."))
		return self.env["ir.actions.actions"]._for_xml_id(self.action_ref)

	@api.model
	def action_by_code(self, code):
		guide = self.search([("code", "=", code)], limit=1) or self.search([("code", "=", "start")], limit=1)
		if not guide:
			raise UserError(_("The guides are not installed; update the AI Agents module."))
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": guide.id, "view_mode": "form",
			"views": [(self.env.ref("veron_ai_agent.guide_view_form").id, "form")], "name": guide.name,
			"target": "current"}


class AiGuideMixin(models.AbstractModel):
	"""The «Guide» button of a section's pages: the guide named in its context"""

	_name = "veron.ai.guide.mixin"
	_description = "Guide Button"

	def action_veron_guide(self):
		return self.env["veron.ai.guide"].action_by_code(self.env.context.get("guide") or "start")


class AiAgentGuide(models.Model):
	_name = "veron.ai.agent"
	_inherit = ["veron.ai.agent", "veron.ai.guide.mixin"]


class AiTemplateGuide(models.Model):
	_name = "veron.ai.agent.template"
	_inherit = ["veron.ai.agent.template", "veron.ai.guide.mixin"]


class AiIntentGuide(models.Model):
	_name = "veron.ai.intent"
	_inherit = ["veron.ai.intent", "veron.ai.guide.mixin"]


class AiPhraseGuide(models.Model):
	_name = "veron.ai.intent.phrase"
	_inherit = ["veron.ai.intent.phrase", "veron.ai.guide.mixin"]


class AiApprovalGuide(models.Model):
	_name = "veron.ai.approval"
	_inherit = ["veron.ai.approval", "veron.ai.guide.mixin"]


class AiRunGuide(models.Model):
	_name = "veron.ai.run"
	_inherit = ["veron.ai.run", "veron.ai.guide.mixin"]


class AiToolGuide(models.Model):
	_name = "veron.ai.tool"
	_inherit = ["veron.ai.tool", "veron.ai.guide.mixin"]


class AiProviderGuide(models.Model):
	_name = "veron.ai.provider"
	_inherit = ["veron.ai.provider", "veron.ai.guide.mixin"]
