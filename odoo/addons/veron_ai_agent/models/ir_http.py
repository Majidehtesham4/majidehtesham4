from odoo import models


class IrHttp(models.AbstractModel):
	_inherit = "ir.http"

	def session_info(self):
		info = super().session_info()
		info["veron_ai_assistant"] = self.env["veron.ai.conversation"]._assistant_shown()
		return info
