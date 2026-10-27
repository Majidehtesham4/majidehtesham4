"""The name of the platform is not shown to people: «Odoo» in the role library and in the agents made from it
becomes «برنامه» (the program)."""

TEMPLATE_FIELDS = ("name", "description", "goal", "instructions", "expected_output")
AGENT_FIELDS = ("name", "description", "goal", "instructions", "expected_output")


def migrate(cr, version):
	for field in TEMPLATE_FIELDS:
		# Translated fields are jsonb by language; each language's text is replaced
		cr.execute(f"""
			UPDATE veron_ai_agent_template SET {field} = (
				SELECT jsonb_object_agg(key, replace(replace(value, 'در Odoo', 'در برنامه'), 'Odoo', 'برنامه'))
				FROM jsonb_each_text({field}))
			WHERE {field}::text LIKE '%%Odoo%%'
		""")
	for field in AGENT_FIELDS:
		cr.execute(f"""
			UPDATE veron_ai_agent SET {field} = replace(replace({field}, 'در Odoo', 'در برنامه'), 'Odoo', 'برنامه')
			WHERE {field} LIKE '%%Odoo%%'
		""")
