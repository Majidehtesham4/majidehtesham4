"""How an assistant makes a draft invoice: where the taxes, the price and the discount of a line come from, and what
is done when stock is short. Decisions of the business, set by an AI manager for a company, and for one assistant
when it should work otherwise; every change is kept in the audit of the AI agents. A change applies to the
requests made after it: drafts already made are never changed by it."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TAXES = [
	("system", "The Current Tax Setting; Asked When It Differs From the Last Invoice or Is Missing"),
	("history", "The Last Posted Invoice of the Same Customer and Product; Asked When There Is None"),
	("ask", "Ask Each Time"),
	("none", "No Taxes Unless Said"),
]
PRICES = [
	("pricelist", "Price List, Then the Product's Current Price"),
	("pricelist_history", "Price List, Then the Customer's Last Price of the Product, Then the Product's Price"),
]
DISCOUNTS = [
	("last", "The Discount of the Last Posted Sale of the Same Product to the Same Customer"),
	("consistent", "The Same Discount of the Last Sales of the Product to the Customer, Only When They Agree"),
	("pricelist", "The Discount of the Price List or Agreed Contract"),
	("ask", "Ask When Not Said"),
	("none", "No Automatic Discount"),
]
STOCK = [
	("report", "Report the Stock Only"),
	("ask", "Report, and Offer a Purchase Draft for What Is Short"),
	("draft", "Report, and Make a Purchase Draft for What Is Short (Never Confirmed)"),
]
# What a new policy has; an update keeps what a company had (see the migration of 19.0.1.1.0)
DEFAULTS = {"taxes_mode": "system", "price_mode": "pricelist", "discount_mode": "last", "history_count": 3,
	"stock_mode": "report"}
FIELDS = tuple(DEFAULTS)


class InvoicePolicy(models.Model):
	_name = "veron.ai.invoice.policy"
	_description = "Draft Invoice Policy of an Assistant"
	_inherit = ["mail.thread"]
	_order = "company_id, agent_id"

	name = fields.Char(compute="_compute_name")
	active = fields.Boolean(default=True, tracking=True)
	company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True,
		tracking=True)
	agent_id = fields.Many2one("veron.ai.agent", "Assistant", ondelete="cascade", index=True, tracking=True,
		help="Only this assistant works this way; empty, all the assistants and agents of the company")
	taxes_mode = fields.Selection(TAXES, "Taxes", required=True, default=DEFAULTS["taxes_mode"], tracking=True,
		help="When the request does not say «with taxes» or «without taxes». Taxes are never added or taken off "
		"silently: what is used is shown with the draft")
	price_mode = fields.Selection(PRICES, "Price", required=True, default=DEFAULTS["price_mode"], tracking=True,
		help="When the request does not say the price. A line with no price stops the draft: nothing is made")
	discount_mode = fields.Selection(DISCOUNTS, "Discount", required=True, default=DEFAULTS["discount_mode"],
		tracking=True, help="When the request does not say the discount of a line. A discount of another product or "
		"another customer is never used; drafts, cancelled invoices and credit notes do not count")
	history_count = fields.Integer("Sales That Must Agree", default=DEFAULTS["history_count"], tracking=True,
		help="For «only when they agree»: how many of the last sales of the product to the customer are compared")
	stock_mode = fields.Selection(STOCK, "Short Stock", required=True, default=DEFAULTS["stock_mode"], tracking=True,
		help="The stock never changes the invoice: a purchase draft is a document of its own, never confirmed here")

	@api.depends("company_id", "agent_id")
	def _compute_name(self):
		for policy in self:
			policy.name = f"{policy.company_id.name} - {policy.agent_id.name or _('All Assistants')}"

	@api.constrains("company_id", "agent_id", "active")
	def _check_one(self):
		for policy in self.filtered("active"):
			if self.search_count([("id", "!=", policy.id), ("company_id", "=", policy.company_id.id),
					("agent_id", "=", policy.agent_id.id or False)]):
				raise ValidationError(_("There is already a policy for this company and assistant."))
			if policy.history_count < 1:
				raise ValidationError(_("At least one sale is compared."))

	@api.model
	def _for(self, company, agent=None):
		"""The policy an assistant follows in a company: its own, else the company's, else the defaults; as a dict
		with the record it came from"""
		Policy = self.sudo()
		policy = agent and Policy.search([("company_id", "=", company.id), ("agent_id", "=", agent.id)], limit=1)
		policy = policy or Policy.search([("company_id", "=", company.id), ("agent_id", "=", False)], limit=1)
		values = {key: policy[key] for key in FIELDS} if policy else dict(DEFAULTS)
		values["policy"] = policy.name if policy else _("Defaults")
		return values

	def _audit(self, event, before=None):
		Audit = self.env["veron.ai.audit"]
		for policy in self:
			after = {key: policy[key] for key in FIELDS}
			Audit._log(event, agent=policy.agent_id or None, description=_("Draft invoice policy «%s»", policy.name),
				data={"before": (before or {}).get(policy.id), "after": after, "company": policy.company_id.name})

	@api.model_create_multi
	def create(self, vals_list):
		policies = super().create(vals_list)
		policies._audit("invoice_policy_created")
		return policies

	def write(self, vals):
		before = {policy.id: {key: policy[key] for key in FIELDS} for policy in self}
		result = super().write(vals)
		self._audit("invoice_policy_changed", before)
		return result

	def unlink(self):
		self._audit("invoice_policy_removed")
		return super().unlink()
