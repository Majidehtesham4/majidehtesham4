import datetime
from odoo.addons.veron_core.models import jalali
company = env.company
company.write({"name": "شرکت بازرگانی آریا تجارت", "vat": "411234567891", "street": "خیابان ولیعصر، پلاک ۱۲۴", "city": "تهران",
	"zip": "1517843311", "phone": "021-88776655"})
admin = env.ref("base.user_admin")
admin.write({"name": "سارا محمدی", "lang": "fa_IR", "tz": "Asia/Tehran"})
admin.partner_id.write({"name": "سارا محمدی"})
Partner = env["res.partner"]
customers = [Partner.create({"name": n, "vat": v, "city": c, "street": s, "zip": z, "phone": p, "is_company": True})
	for n, v, c, s, z, p in [
	("فروشگاه زنجیره‌ای نگین", "411122223333", "تهران", "بلوار میرداماد، پلاک ۴۵", "1911734561", "021-22114455"),
	("شرکت پخش البرز", "411155556666", "کرج", "میدان آزادگان، خیابان دانش", "3134567812", "026-34456677"),
	("بازرگانی پارسیان", "411177778888", "اصفهان", "خیابان چهارباغ عباسی", "8174673451", "031-32223344"),
	("هتل آسمان شیراز", "411199990000", "شیراز", "بلوار زند", "7134845612", "071-36667788")]]
vendor = Partner.create({"name": "توزیع کالای دیجیتال پارس", "vat": "411100001111", "city": "تهران", "is_company": True})
tax = env["account.tax"].search([("type_tax_use", "=", "sale"), ("amount", "=", 10), ("company_id", "=", company.id)], limit=1)
print("tax", tax.name, tax.amount)
Product = env["product.product"]
products = [Product.create({"name": n, "list_price": p, "default_code": c, "taxes_id": [(6, 0, tax.ids)], "type": "consu"})
	for n, p, c in [("لپ‌تاپ ایسوس ۱۵ اینچ", 520_000_000, "LP-1501"), ("مانیتور ۲۷ اینچ سامسونگ", 185_000_000, "MN-2701"),
		("کیبورد و ماوس بی‌سیم", 12_500_000, "KB-0310"), ("پرینتر لیزری اچ‌پی", 96_000_000, "PR-0420"),
		("هارد اکسترنال ۲ ترابایت", 38_000_000, "HD-0200")]]
today = datetime.date.today()
Move = env["account.move"]
import random
random.seed(5)
for i in range(14):
	d = today - datetime.timedelta(days=random.randint(1, 50))
	lines = [(0, 0, {"product_id": p.id, "quantity": random.choice([1, 2, 3, 5]), "tax_ids": [(6, 0, tax.ids)]})
		for p in random.sample(products, random.randint(1, 3))]
	inv = Move.create({"move_type": "out_invoice", "partner_id": random.choice(customers).id, "invoice_date": d, "date": d,
		"invoice_line_ids": lines})
	inv.action_post()
for i in range(4):
	d = today - datetime.timedelta(days=random.randint(5, 40))
	bill = Move.create({"move_type": "in_invoice", "partner_id": vendor.id, "invoice_date": d, "date": d,
		"invoice_line_ids": [(0, 0, {"product_id": random.choice(products).id, "quantity": 4, "price_unit": 300_000_000, "tax_ids": []})]})
	bill.action_post()
bank = env["res.bank"].search([], limit=3) or env["res.bank"].create([{"name": "بانک ملت"}, {"name": "بانک ملی ایران"}, {"name": "بانک صادرات ایران"}])
bank_names = ["بانک ملت", "بانک ملی ایران", "بانک صادرات ایران", "بانک پاسارگاد"]
banks = env["res.bank"].browse()
for n in bank_names:
	banks |= env["res.bank"].search([("name", "=", n)], limit=1) or env["res.bank"].create({"name": n})
Cheque = env["veron.cheque"]
for i in range(7):
	ch = Cheque.create({"direction": "in", "partner_id": random.choice(customers).id, "amount": random.choice([150, 240, 380, 520, 75]) * 1_000_000,
		"sayad_id": "".join(random.choice("0123456789") for _ in range(16)), "serial": str(random.randint(100000, 999999)),
		"bank_id": random.choice(banks).id, "branch": random.choice(["شعبه ونک", "شعبه مرکزی", "شعبه سعادت‌آباد"]),
		"due_date": today + datetime.timedelta(days=random.randint(-5, 60))})
	try:
		ch.action_receive()
	except Exception as e:
		print("receive", e)
env.cr.commit()
print("done", len(customers), Move.search_count([]), Cheque.search_count([]))
A = env["account.account"]
c = env.company
def acc(code, name, t="asset_current"):
	return A.search([("code", "=", code)], limit=1) or A.create({"code": code, "name": name, "account_type": t, "reconcile": True})
c.veron_cheque_hand_account_id = acc("111201", "چک‌های دریافتنی نزد صندوق")
c.veron_cheque_collection_account_id = acc("111202", "چک‌های در جریان وصول")
c.veron_cheque_bounced_account_id = A.search([("code", "=", "111306")], limit=1)
c.veron_cheque_payable_account_id = A.search([("code", "=", "211101")], limit=1)
for ch in env["veron.cheque"].search([("state", "=", "draft")]):
	ch.action_receive()
print([ (x.name, x.state) for x in env["veron.cheque"].search([])])
env.cr.commit()
bank = env["account.journal"].search([("type", "=", "bank")], limit=1)
print("bank", bank.name)
env["veron.cheque"].search([]).write({"bank_journal_id": bank.id})
env.ref("base.partner_root").name = "VeronBot"
env.cr.commit()
