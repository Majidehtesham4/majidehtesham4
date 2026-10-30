"""The draft invoice rules move from three global settings to a policy of each company (and of an assistant when
it should work otherwise). An update must not change how taxes or discounts are decided without anyone choosing
it, so each company gets a policy written from what it had:

- taxes: «ask» stays «ask»; «product» (the product's taxes) becomes «system», the same taxes, asked only when the
  customer's last invoice of the product had others; «none» stays «none»; not set, «ask» - the assistant asks
  rather than decide anything it did not decide before
- discount: «consistent» stays; «said» becomes «none» (no automatic discount); not set, «last» - the discount of
  the last posted sale of the same product to the same customer, as the assistant did before these settings
- price: kept when set; not set, «pricelist»: the price list, then the product's current price, as an old price
  of a customer is not used unless a business chooses it. The draft always says where each price came from
- short stock: «report», only reported, as nothing was done with the stock before

The policies can be changed in AI Agents, Configuration, Draft Invoice Policies."""

from odoo import SUPERUSER_ID, api

PARAMS = ("veron_ai_agent_account.invoice_taxes", "veron_ai_agent_account.invoice_price",
	"veron_ai_agent_account.invoice_discount")


def migrate(cr, version):
	env = api.Environment(cr, SUPERUSER_ID, {})
	Param = env["ir.config_parameter"].sudo()
	taxes, price, discount = (Param.get_param(name) for name in PARAMS)
	values = {
		"taxes_mode": {"ask": "ask", "product": "system", "none": "none"}.get(taxes, "ask"),
		"discount_mode": {"consistent": "consistent", "said": "none"}.get(discount, "last"),
		"price_mode": price if price in ("pricelist", "pricelist_history") else "pricelist",
		"stock_mode": "report",
	}
	Policy = env["veron.ai.invoice.policy"].with_context(active_test=False)
	for company in env["res.company"].search([]):
		if not Policy.search_count([("company_id", "=", company.id), ("agent_id", "=", False)]):
			Policy.create(dict(values, company_id=company.id))
	for name in PARAMS:
		Param.search([("key", "=", name)]).unlink()
	# The taxes of a draft are no longer read from a setting by the assistant: the policy decides line by line
	intent = env["veron.ai.intent"].with_context(active_test=False).search([("code", "=", "sale_invoice_draft")], limit=1)
	if intent:
		import json

		slots = intent._slots()
		for slot in slots:
			if slot.get("arg") == "taxes" and slot.get("param") == PARAMS[0]:
				slot.pop("param")
				slot.pop("question", None)
				slot["required"] = False
		intent.slots = json.dumps(slots, ensure_ascii=False)
