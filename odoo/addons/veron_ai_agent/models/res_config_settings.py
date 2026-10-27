from odoo import fields, models


class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	veron_ai_max_upload_mb = fields.Integer("Largest File (MB)", default=10, config_parameter="veron_ai_agent.max_upload_mb")
	veron_ai_audio_retention_days = fields.Integer("Keep Voice Messages (Days)", default=30,
		config_parameter="veron_ai_agent.audio_retention_days")
	veron_ai_keep_audio = fields.Boolean("Keep the Voice After Its Text", config_parameter="veron_ai_agent.keep_audio")
	veron_ai_file_retention_days = fields.Integer("Keep Photos and PDFs (Days, 0: Always)", default=0,
		config_parameter="veron_ai_agent.file_retention_days")
	veron_ai_audit_retention_days = fields.Integer("Keep Audit Events (Days, 0: Always)", default=0,
		config_parameter="veron_ai_agent.audit_retention_days")
