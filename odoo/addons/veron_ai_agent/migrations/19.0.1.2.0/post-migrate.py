"""«Odoo» was first written «برنامه» in the role library and the agents made from it; it is «Veron» now."""

PHRASES = (("در برنامه", "در Veron"), ("قیمت‌های برنامه", "قیمت‌های Veron"), ("داده‌ی برنامه", "داده‌ی Veron"))
FIELDS = ("name", "description", "goal", "instructions", "expected_output")


def _replace(expression):
	for old, new in PHRASES:
		expression = f"replace({expression}, '{old}', '{new}')"
	return expression


def migrate(cr, version):
	for field in FIELDS:
		cr.execute(f"""
			UPDATE veron_ai_agent_template SET {field} = (
				SELECT jsonb_object_agg(key, {_replace('value')}) FROM jsonb_each_text({field}))
			WHERE {field}::text LIKE '%%برنامه%%'
		""")
		cr.execute(f"UPDATE veron_ai_agent SET {field} = {_replace(field)} WHERE {field} LIKE '%%برنامه%%'")
