import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
	"""Companies in Iran (or with no country yet) that have recorded nothing get OCA's Iranian chart of
	accounts. Odoo itself has no Iranian chart, so a new database in Iran starts on the generic one;
	a company with entries keeps its chart, which can only be changed before anything is recorded."""
	iran = env.ref("base.ir")
	for company in env["res.company"].search([]):
		if company.country_id and company.country_id != iran:
			continue
		if company.chart_template == "ir":
			continue
		if env["account.move"].search_count([("company_id", "=", company.id)], limit=1):
			_logger.info("ERP-VERON: %s has entries; its chart of accounts is kept", company.name)
			continue
		company.country_id = iran
		env["account.chart.template"].try_loading("ir", company, install_demo=False)
		_logger.info("ERP-VERON: the Iranian chart of accounts is loaded for %s", company.name)
