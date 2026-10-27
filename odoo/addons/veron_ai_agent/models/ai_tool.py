import json

from odoo import api, fields, models

from ..services import registry


class AiTool(models.Model):
	_name = "veron.ai.tool"
	_description = "Agent Tool"
	_order = "category, code"

	code = fields.Char(required=True, readonly=True, index=True)
	name = fields.Char(required=True, translate=True)
	description = fields.Text(translate=True)
	category = fields.Selection(registry.CATEGORIES, readonly=True)
	action = fields.Selection([("read", "Read"), ("suggest", "Suggest"), ("draft", "Draft"), ("execute", "Act")],
		readonly=True, help="Read: level 1; suggest: level 2; draft: level 3; act: level 4")
	level = fields.Integer("Needs Level", readonly=True)
	risk = fields.Selection(registry.RISKS, readonly=True)
	sensitive = fields.Selection(registry.SENSITIVE, "Sensitive Action", readonly=True,
		help="Always needs a person's approval, unless a manager sets an explicit rule for it")
	models_used = fields.Char("Models", readonly=True)
	module = fields.Char(readonly=True)
	supervisor_only = fields.Boolean(readonly=True)
	input_schema = fields.Text("Arguments", readonly=True)
	registered = fields.Boolean(readonly=True, help="The code of the tool is installed")
	available = fields.Boolean(compute="_compute_available", help="Installed, with the models it needs")

	_code_unique = models.Constraint("unique (code)", "A tool code is unique.")

	def _compute_available(self):
		for record in self:
			tool = registry.get(record.code)
			record.available = bool(tool and tool.available(self.env))

	@api.model
	def _sync(self):
		"""The records of the tools installed in the code; a tool whose code is gone is kept, unregistered"""
		existing = {record.code: record for record in self.with_context(active_test=False).search([])}
		for code, tool in registry.TOOLS.items():
			values = {
				"name": tool.name, "description": tool.description, "category": tool.category, "action": tool.action,
				"level": tool.level, "risk": tool.risk, "sensitive": tool.sensitive or False,
				"models_used": ", ".join(tool.models), "module": tool.module, "supervisor_only": tool.supervisor_only,
				"input_schema": json.dumps(tool.schema, ensure_ascii=False, indent=1), "registered": True,
			}
			if code in existing:
				# The name and the description keep their translations
				existing[code].write({k: v for k, v in values.items() if k not in ("name", "description")})
			else:
				self.create({"code": code, **values})
		gone = [record for code, record in existing.items() if code not in registry.TOOLS]
		for record in gone:
			record.registered = False
		return True

	@api.model
	def _by_codes(self, codes):
		codes = [c.strip() for c in (codes or "").split(",") if c.strip()]
		if codes and self.search_count([("code", "in", codes)]) < len(set(codes)):
			self._sync()
		return self.search([("code", "in", codes)])
