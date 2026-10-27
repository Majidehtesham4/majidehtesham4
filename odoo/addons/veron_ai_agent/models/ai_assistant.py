"""The assistant of the chat box on every page: one agent every internal user may use, each with their own
access rights. Its tools are granted at authority 3: it reads and makes drafts; an action waits for
approval, by the person who asked when it is not a sensitive one, and a sensitive one (posting, payment,
publishing...) by the people its manager names."""

from odoo import api, models

from ..services import registry

# Records people ask about everywhere; each person still sees only what their own rights allow
COMMON_MODELS = ["res.partner", "product.product", "product.template", "sale.order", "purchase.order", "account.move",
	"account.move.line", "account.journal", "stock.picking", "stock.quant", "hr.employee", "project.task", "mail.activity",
	"document.page"]


class AiAgentAssistant(models.Model):
	_inherit = "veron.ai.agent"

	@api.model
	def _setup_assistant(self):
		"""The assistant's grants, data and companies, brought up to the tools installed"""
		agent = self.env.ref("veron_ai_agent.agent_assistant", raise_if_not_found=False)
		if not agent:
			return False
		agent = agent.sudo().with_context(active_test=False)
		self.env["veron.ai.tool"]._sync()
		Tool = self.env["veron.ai.tool"].with_context(active_test=False)
		granted = set(agent.grant_ids.tool_id.mapped("code"))
		grants, models_wanted = [], set(COMMON_MODELS)
		for code, tool in registry.TOOLS.items():
			if tool.supervisor_only or not tool.available(self.env):
				continue
			models_wanted.update(tool.models)
			if code in granted:
				continue
			record = Tool.search([("code", "=", code)], limit=1)
			if record:
				grants.append((0, 0, {"tool_id": record.id, "level": "3",
					"requester_may_approve": not tool.sensitive}))
		scoped = set(agent.scope_ids.model_id.mapped("model"))
		scopes = [(0, 0, {"model_id": self.env["ir.model"]._get_id(name)}) for name in sorted(models_wanted)
			if name in self.env and name not in scoped]
		values = {"company_ids": [(6, 0, self.env["res.company"].sudo().search([]).ids)]}
		if grants:
			values["grant_ids"] = grants
		if scopes:
			values["scope_ids"] = scopes
		agent.write(values)
		return True
