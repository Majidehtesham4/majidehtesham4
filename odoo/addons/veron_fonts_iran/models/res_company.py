from odoo import fields, models

FONTS = [("Vazirmatn", "Vazirmatn"), ("Sahel", "Sahel"), ("Shabnam", "Shabnam"), ("Samim", "Samim"), ("Tahoma", "Tahoma")]


class ResCompany(models.Model):
	_inherit = "res.company"

	veron_report_font = fields.Selection(FONTS, "Font of Printed Documents", default="Vazirmatn",
		help="The font of the invoices, vouchers, payslips and letters printed for this company")
