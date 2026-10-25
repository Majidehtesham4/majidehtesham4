import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
	"""Companies in Iran, with no country yet, or on Odoo's generic chart (which also sets the country
	to the United States) that have recorded nothing get OCA's Iranian chart of accounts. Odoo itself
	has no Iranian chart, so a new database in Iran starts on the generic one; a company with entries
	keeps its chart, which can only be changed before anything is recorded.

	When account is installed in the same run, Odoo loads its generic chart once every module is
	loaded, after this hook, and would replace ours: the Iranian chart is loaded in its place then."""
	pending = getattr(env.registry, "_auto_install_template", None)
	if not pending:
		load_iranian_chart(env)
		return

	def load_after_modules(env):
		load_iranian_chart(env)
		# A company outside Iran still gets the chart Odoo chose for it
		if not env.company.chart_template:
			pending(env)

	env.registry._auto_install_template = load_after_modules


def load_iranian_chart(env):
	iran = env.ref("base.ir")
	for company in env["res.company"].search([]):
		if company.country_id and company.country_id != iran and company.chart_template != "generic_coa":
			continue
		if company.chart_template == "ir":
			continue
		if env["account.move"].search_count([("company_id", "=", company.id)], limit=1):
			_logger.info("ERP-VERON: %s has entries; its chart of accounts is kept", company.name)
			continue
		company.country_id = iran
		env["account.chart.template"].try_loading("ir", company, install_demo=False)
		_logger.info("ERP-VERON: the Iranian chart of accounts is loaded for %s", company.name)
