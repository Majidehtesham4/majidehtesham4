"""Default prompts, as in Odoo's AI app: what the assistant is told on the records of a model, and buttons of
ready requests shown in the chat box there"""

from odoo import api, fields, models


class AiPromptRule(models.Model):
	_name = "veron.ai.prompt.rule"
	_description = "AI Default Prompt"
	_order = "sequence, id"

	name = fields.Char("Rule Name", required=True, translate=True)
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	model_ids = fields.Many2many("ir.model", string="On the Records", help="Empty: on every page")
	agent_id = fields.Many2one("veron.ai.agent", "For the Agent", help="Empty: for every agent")
	instructions = fields.Text(translate=True, help="What the agent is told about the records of these pages")
	button_ids = fields.One2many("veron.ai.prompt.button", "rule_id", "Buttons", copy=True)

	@api.model
	def _for(self, model_name, agent=None):
		rules = self.sudo().search([])
		return rules.filtered(lambda r: (not r.model_ids or model_name in r.model_ids.mapped("model"))
			and (not r.agent_id or not agent or r.agent_id == agent))

	@api.model
	def veron_prompts(self, model_name=False, agent_id=False):
		"""The buttons of the chat box on a page"""
		agent = self.env["veron.ai.agent"].browse(agent_id) if agent_id else None
		buttons = self._for(model_name or "", agent).button_ids.sorted(lambda b: (b.rule_id.sequence, b.sequence))
		return [{"id": b.id, "title": b.title, "prompt": b.prompt} for b in buttons[:8]]


class AiPromptButton(models.Model):
	_name = "veron.ai.prompt.button"
	_description = "AI Default Prompt Button"
	_order = "sequence, id"

	rule_id = fields.Many2one("veron.ai.prompt.rule", required=True, ondelete="cascade")
	sequence = fields.Integer(default=10)
	title = fields.Char(required=True, translate=True)
	prompt = fields.Text(required=True, translate=True)


class AiRunPromptRule(models.Model):
	_inherit = "veron.ai.run"

	def _system_prompt(self):
		prompt = super()._system_prompt()
		if self.page_model:
			rules = self.env["veron.ai.prompt.rule"]._for(self.page_model, self.agent_id).filtered("instructions")
			if rules:
				prompt += "\n\nOn this page:\n" + "\n".join(rules.mapped("instructions"))
		return prompt
