import json
import re

from odoo import http
from odoo.http import request

from odoo.addons.spreadsheet_dashboard.controllers.dashboards_controllers import DashboardDataRoute


class VeronDashboardDataRoute(DashboardDataRoute):
	@http.route()
	def get_dashboard_data(self, dashboard):
		response = super().get_dashboard_data(dashboard)
		try:
			data = json.loads(response.get_data())
		except ValueError:
			return response
		if not data.get("is_sample"):
			return response
		# A sample is sent by Odoo without its module (so its words stay in English) and without the currency
		dashboard = dashboard.exists()
		data.setdefault("translation_namespace", dashboard._get_dashboard_translation_namespace())
		data.setdefault("default_currency", request.env["res.currency"].get_company_currency_for_spreadsheet())
		data.setdefault("revisions", [])
		snapshot = data.get("snapshot") or {}
		# The sample's made-up amounts are written in dollars in Odoo's files: shown without a currency here
		snapshot = json.loads(re.sub(r"\[\$\$\]", "", json.dumps(snapshot)))
		snapshot.setdefault("settings", {})["locale"] = request.env["res.lang"]._get_user_spreadsheet_locale()
		data["snapshot"] = snapshot
		return request.make_json_response(data)
