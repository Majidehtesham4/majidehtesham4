"""The agent's page and the chat window as in Odoo's AI app: the menu «Settings» of the app is now «Configuration»,
in Persian too (a translation the database already has is not replaced by the module's file)"""


def migrate(cr, version):
	cr.execute("""
		UPDATE ir_ui_menu m SET name = m.name || '{"fa_IR": "پیکربندی"}'::jsonb
		  FROM ir_model_data d
		 WHERE d.model = 'ir.ui.menu' AND d.module = 'veron_ai_agent' AND d.name = 'menu_config' AND d.res_id = m.id
		   AND m.name ? 'fa_IR'
	""")
