from odoo import api, models


class AccountPaymentMethodLine(models.Model):
	"""A way of paying of a journal is named after its method in the company's language, not in the language of
	whoever made the journal (the chart is often installed in English, and its bank journal then says «Manual
	Payment» to people who read Persian)"""
	_inherit = "account.payment.method.line"

	@api.depends("payment_method_id")
	def _compute_name(self):
		for line in self:
			if not line.name:
				lang = line.journal_id.company_id.partner_id.lang or self.env.lang
				line.name = line.payment_method_id.with_context(lang=lang).name

	@api.model_create_multi
	def create(self, vals_list):
		# the journal gives the method's name as it reads in its own language: named again in the company's
		lines = super().create(vals_list)
		lines._veron_rename()
		return lines

	def _veron_rename(self):
		"""The lines still named in English after their method: named in their company's language (all of them
		when called on none)"""
		for line in self or self.search([]):
			lang = line.journal_id.company_id.partner_id.lang
			method = line.payment_method_id
			if lang and line.name == method.with_context(lang="en_US").name:
				name = method.with_context(lang=lang).name
				if name != line.name:
					line.name = name
