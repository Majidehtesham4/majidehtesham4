import io

from odoo import fields
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.veron_ai_agent.tests.common import FakeAdapter


def image(color, size=(40, 30)):
	from PIL import Image

	buffer = io.BytesIO()
	Image.new("RGB", size, color).save(buffer, "JPEG", quality=95)
	return buffer.getvalue()


class FinanceCase(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notrack=True))
		cls.company = cls.env.company
		groups_accountant = "base.group_user,account.group_account_user,veron_ai_agent.group_ai_user"
		cls.accountant = new_test_user(cls.env, "pc_accountant", groups=groups_accountant)
		cls.custodian = new_test_user(cls.env, "pc_custodian", groups="base.group_user")
		cls.other_custodian = new_test_user(cls.env, "pc_other", groups="base.group_user")
		Account = cls.env["account.account"]
		cls.cash_account = Account.search([("code", "=", "111003"), ("company_ids", "in", cls.company.id)], limit=1) or \
			Account.create({"name": "Petty cash", "code": "111993", "account_type": "asset_cash", "company_ids": [(6, 0, cls.company.ids)]})
		cls.expense_account = Account.search([("account_type", "=", "expense"), ("company_ids", "in", cls.company.id)], limit=1)
		cls.journal = cls.env["account.journal"].search([("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1)
		cls.bank = cls.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1)
		Category = cls.env["veron.petty.cash.category"]
		cls.cat_office = Category.create({"name": "لوازم اداری", "account_id": cls.expense_account.id})
		cls.cat_taxi = Category.create({"name": "ایاب و ذهاب", "account_id": cls.expense_account.id, "max_amount": 2_000_000})
		cls.fund = cls.env["veron.petty.cash.fund"].create({
			"name": "تنخواه نمایشگاه", "custodian_user_id": cls.custodian.id, "account_id": cls.cash_account.id,
			"journal_id": cls.journal.id, "amount": 50_000_000, "max_receipt_amount": 10_000_000,
			"category_ids": [(6, 0, (cls.cat_office | cls.cat_taxi).ids)],
		})
		cls.other_fund = cls.env["veron.petty.cash.fund"].create({
			"name": "تنخواه انبار", "custodian_user_id": cls.other_custodian.id, "account_id": cls.cash_account.id,
			"journal_id": cls.journal.id, "amount": 10_000_000,
		})
		Provider = cls.env["veron.ai.provider"]
		cls.llm = Provider.create({"name": "Fake", "kind": "llm", "adapter": "test_fake", "is_default": True, "api_key": "k"})
		cls.vision = Provider.create({"name": "Fake vision", "kind": "vision", "adapter": "test_fake", "is_default": True,
			"api_key": "k"})
		cls.env["veron.ai.tool"]._sync()

	def setUp(self):
		super().setUp()
		FakeAdapter.script, FakeAdapter.calls, FakeAdapter.error = [], [], None

	def topup(self, amount, date):
		"""Money given to the custodian, posted from the bank"""
		move = self.env["account.move"].create({"move_type": "entry", "journal_id": self.journal.id, "date": date, "line_ids": [
			(0, 0, {"account_id": self.cash_account.id, "partner_id": self.custodian.partner_id.id, "debit": amount}),
			(0, 0, {"account_id": self.bank.default_account_id.id, "credit": amount}),
		]})
		move.action_post()
		return move

	def agent(self, level, codes, models, **values):
		Tool = self.env["veron.ai.tool"]
		vals = {
			"name": values.pop("name", "عامل مالی"), "enabled": True, "authority_level": level,
			"company_ids": [(6, 0, self.company.ids)], "responsible_user_id": self.accountant.id,
			"user_ids": [(6, 0, (self.accountant | self.custodian).ids)], "llm_provider_id": self.llm.id,
			"vision_provider_id": self.vision.id,
			"grant_ids": [(0, 0, {"tool_id": Tool._by_codes(code).id, "level": level}) for code in codes],
			"scope_ids": [(0, 0, {"model_id": self.env["ir.model"]._get_id(model)}) for model in models],
		}
		vals.update(values)
		return self.env["veron.ai.agent"].create(vals)

	def start(self, agent, script, user=None, text="انجام بده"):
		FakeAdapter.script = list(script)
		user = user or self.accountant
		return self.env["veron.ai.run"].with_user(user)._start(agent, user, "user", text=text)

	@staticmethod
	def today():
		return fields.Date.today()
