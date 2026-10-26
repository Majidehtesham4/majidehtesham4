from odoo import api, fields, models

# The accounts of the Iranian chart a cheque goes through, by code
DEFAULT_CODES = {
	"veron_cheque_hand_account_id": "111203",
	"veron_cheque_collection_account_id": "111201",
	"veron_cheque_bounced_account_id": "111306",
	"veron_cheque_payable_account_id": "211101",
}


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_cheque_hand_account_id = fields.Many2one("account.account", "Cheques in Hand")
	veron_cheque_collection_account_id = fields.Many2one("account.account", "Cheques in Collection")
	veron_cheque_bounced_account_id = fields.Many2one("account.account", "Bounced Cheques")
	veron_cheque_payable_account_id = fields.Many2one("account.account", "Notes Payable")
	veron_cheque_journal_id = fields.Many2one("account.journal", "Cheque Journal")

	def _veron_cheque_setup(self):
		"""The accounts of the Iranian chart and a journal for the cheques' entries, where not set yet"""
		Account = self.env["account.account"]
		for company in self:
			values = {}
			for field, code in DEFAULT_CODES.items():
				if not company[field]:
					account = Account.with_company(company).search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
					if account:
						values[field] = account.id
			if not company.veron_cheque_journal_id:
				journal = self.env["account.journal"].search([("company_id", "=", company.id), ("code", "=", "چک")], limit=1)
				journal = journal or self.env["account.journal"].create({
					"name": "چک‌ها", "code": "چک", "type": "general", "company_id": company.id})
				values["veron_cheque_journal_id"] = journal.id
			if values:
				company.write(values)

	@api.model
	def _veron_cheque_setup_all(self):
		self.search([("chart_template", "!=", False)])._veron_cheque_setup()


class ResConfigSettings(models.TransientModel):
	_inherit = "res.config.settings"

	veron_cheque_hand_account_id = fields.Many2one(related="company_id.veron_cheque_hand_account_id", readonly=False)
	veron_cheque_collection_account_id = fields.Many2one(related="company_id.veron_cheque_collection_account_id", readonly=False)
	veron_cheque_bounced_account_id = fields.Many2one(related="company_id.veron_cheque_bounced_account_id", readonly=False)
	veron_cheque_payable_account_id = fields.Many2one(related="company_id.veron_cheque_payable_account_id", readonly=False)
	veron_cheque_journal_id = fields.Many2one(related="company_id.veron_cheque_journal_id", readonly=False)
