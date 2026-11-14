"""The small analyses of business.py: what they give back is what their description promises"""

import json
from datetime import datetime

from odoo.tests import new_test_user, tagged

from .common import AgentCase, calls


@tagged("post_install", "-at_install")
class TestSalesSummary(AgentCase):
	def test_by_day_in_the_persons_own_days(self):
		if "sale.order" not in self.env:
			self.skipTest("Sales is not installed here")
		seller = new_test_user(self.env, "ai_seller", groups="base.group_user,veron_ai_agent.group_ai_user,"
			"sales_team.group_sale_salesman_all_leads", company_ids=[(6, 0, self.company_a.ids)],
			company_id=self.company_a.id, tz="Asia/Tehran")
		product = self.env["product.product"].create({"name": "کالای آزمایشی", "lst_price": 100, "taxes_id": [(5, 0, 0)]})

		def order(moment, quantity):
			sale = self.env["sale.order"].create({"partner_id": self.partner_a.id, "company_id": self.company_a.id,
				"order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": quantity, "price_unit": 100,
					"tax_ids": [(5, 0, 0)]})]})
			sale.action_confirm()
			# Confirming sets the moment to now; the moment of the order is set after it, in UTC as stored
			sale.date_order = moment
			return sale

		# 2 November 1:30 a.m. in Tehran is still 1 November in UTC: of the 2nd for the person
		order(datetime(2026, 11, 1, 22, 0), 1)
		order(datetime(2026, 11, 2, 8, 0), 2)
		# 3 November 0:30 a.m. in Tehran
		order(datetime(2026, 11, 2, 21, 0), 3)
		# 4 November 0:30 a.m. in Tehran: after the period, though still the 3rd in UTC
		order(datetime(2026, 11, 3, 21, 0), 4)
		agent = self.make_agent("1", ["sales_summary"], user_ids=[(6, 0, seller.ids)], responsible_user_id=seller.id,
			scope_ids=[(0, 0, {"model_id": self.env["ir.model"]._get_id("sale.order")})])
		run = self.start(agent, user=seller, script=[calls(("sales_summary", {"date_from": "2026-11-02",
			"date_to": "2026-11-03"}))])
		self.assertEqual(run.step_ids.decision, "allowed", run.step_ids.output_json)
		result = json.loads(run.step_ids.output_json)
		self.assertEqual(result["orders"], 3)
		self.assertEqual(result["untaxed"], 600)
		self.assertEqual(result["by_day"], [{"date": "2026-11-02", "orders": 2, "untaxed": 300},
			{"date": "2026-11-03", "orders": 1, "untaxed": 300}])
		self.assertEqual(sum(day["orders"] for day in result["by_day"]), result["orders"], "the days add up to the period")
