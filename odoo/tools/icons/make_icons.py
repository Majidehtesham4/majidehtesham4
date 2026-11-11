"""The icons of ERP-VERON's modules, drawn in the manner of Odoo's own: a 50 x 50 grid, flat shapes inside 4..46,
round corners, Odoo's colours, and where two shapes cross a third, darker colour.

    python3 odoo/tools/icons/make_icons.py            # writes static/description/icon.svg of every module
    node odoo/tools/icons/render.js                     # and icon.png (256 x 256) from it

Each module has its own picture: no two are the same."""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addons")

PURPLE, PLUM, WINE = "#985184", "#712258", "#962B48"
PINK, ORANGE, AMBER, YELLOW = "#FC868B", "#F86126", "#F78613", "#FBB945"
TEAL, GREEN, PINE, DEEP = "#1AD3BB", "#03AF89", "#1A6F66", "#005E7A"
SKY, BLUE, NAVY, ROYAL = "#2EBCFA", "#088BF5", "#144496", "#004EFF"
RED, BRICK, INK, GREY, WHITE = "#F9464C", "#953B24", "#081F2C", "#D1D5DB", "#fff"


class Shape:
	def __init__(self, tag, transform=None, **attrs):
		self.tag, self.transform, self.attrs = tag, transform, attrs

	def svg(self, fill, extra=""):
		attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in self.attrs.items())
		t = f' transform="{self.transform}"' if self.transform else ""
		return f'<{self.tag} {attrs}{t} fill="{fill}"{extra}/>'


def rect(x, y, w, h, r=4, rot=None):
	t = f"rotate({rot} {x + w / 2} {y + h / 2})" if rot else None
	return Shape("rect", t, x=x, y=y, width=w, height=h, rx=r)


def circle(cx, cy, r):
	return Shape("circle", cx=cx, cy=cy, r=r)


def path(d, rule=None):
	return Shape("path", **({"d": d, "fill_rule": rule} if rule else {"d": d}))


class Icon:
	def __init__(self):
		self.parts, self.defs, self.n = [], [], 0

	def add(self, shape, fill):
		self.parts.append(shape.svg(fill))
		return self

	def cross(self, a, b, fill):
		"""Where b lies over a, b is drawn in a darker colour"""
		self.n += 1
		cid = f"c{self.n}"
		self.defs.append(f'<clipPath id="{cid}">{a.svg("#000")}</clipPath>')
		self.parts.append(f'<g clip-path="url(#{cid})">{b.svg(fill)}</g>')
		return self

	def line(self, d, color, width=4):
		self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
			'stroke-linejoin="round"/>')
		return self

	def svg(self):
		defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
		return ('<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg">'
			f"{defs}{''.join(self.parts)}</svg>")


def two(a, fa, b, fb, mix):
	return Icon().add(a, fa).add(b, fb).cross(a, b, mix)


# --- the apps of the home screen

def ai_agent():
	left, right = rect(7.5, 4.5, 10, 42, 5, 15.75), rect(18.5, 4.5, 10, 42, 5, -15.75)
	bar = rect(11, 29, 15, 6, 3)
	star = path("M40.5 3c.7 3 2.2 4.5 5.2 5.2-3 .7-4.5 2.2-5.2 5.2-.7-3-2.2-4.5-5.2-5.2 3-.7 4.5-2.2 5.2-5.2Z")
	icon = two(left, PURPLE, right, PINK, WINE).add(bar, YELLOW).cross(right, bar, ORANGE)
	return icon.add(rect(36, 17, 9, 29, 4.5), TEAL).add(star, YELLOW)


def petty_cash():
	note, body = rect(9, 6, 32, 17, 3.5, -10), rect(4, 17, 42, 28, 6)
	clasp = rect(29, 25, 17, 12, 6)
	return two(note, YELLOW, body, PURPLE, PLUM).add(clasp, PINK).add(circle(35.5, 31, 2.2), WHITE)


def secretariat():
	doc, env = rect(12, 4, 26, 30, 4), rect(4, 18, 42, 28, 5)
	flap = path("M4 21 25 35l21-14v7L25 42 4 28Z")
	icon = two(doc, YELLOW, env, PINK, ORANGE)
	return icon.cross(env, flap, WINE).add(rect(17, 10, 16, 3, 1.5), AMBER)


def barcode():
	icon = Icon()
	bars = [(9, 3), (14, 2), (18, 4), (24, 2), (28, 3), (33, 2), (37, 4)]
	laser = rect(4, 22.5, 42, 5, 2.5)
	for x, w in bars:
		icon.add(rect(x, 13, w, 24, 1), PURPLE)
	icon.add(laser, RED)
	for x, w in bars:
		icon.cross(laser, rect(x, 13, w, 24, 1), WINE)
	icon.line("M5 13V9a4 4 0 0 1 4-4h4M37 5h4a4 4 0 0 1 4 4v4M45 37v4a4 4 0 0 1-4 4h-4M13 45H9a4 4 0 0 1-4-4v-4", TEAL, 3.5)
	return icon


def payroll():
	body = path("M4 42c0-8.3 6.7-15 15-15s15 6.7 15 15v1a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3Z")
	coin = circle(35, 30, 11)
	icon = Icon().add(circle(19, 14, 8), PURPLE).add(body, PURPLE).add(coin, YELLOW).cross(body, coin, BRICK)
	return icon.add(rect(32, 23, 6, 14, 3), AMBER)


def shopfloor():
	hall = path("M4 25.5a3 3 0 0 1 1.3-2.5L14 17v6l9.3-6.2A1.8 1.8 0 0 1 26 18.3V23l9.3-6.2A1.8 1.8 0 0 1 38 18.3V46H7a3 3 0 0 1-3-3Z")
	chimney = rect(33, 4, 10, 42, 3)
	icon = Icon().add(hall, TEAL).add(chimney, PURPLE).cross(hall, chimney, DEEP)
	for x in (9, 17, 25):
		icon.add(rect(x, 31, 5, 8, 1.5), YELLOW)
	return icon


def plm():
	icon = Icon().line("M38.5 14.5A17 17 0 1 0 42 25", TEAL, 7)
	icon.add(path("M33 6.5 46 8l-4.5 12Z"), TEAL)
	box = rect(16, 16, 18, 18, 4)
	return icon.add(box, PURPLE).cross(box, rect(25, 16, 9, 18, 0), PLUM)


def rental():
	ring = path("M16 13a12 12 0 1 1 0 24 12 12 0 0 1 0-24Zm0 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9Z", "evenodd")
	shaft = rect(22, 21, 24, 8, 3)
	icon = Icon().add(ring, YELLOW).add(shaft, PINK).cross(ring, shaft, ORANGE)
	return icon.add(rect(35, 27, 5, 9, 2), PINK).add(rect(41.5, 27, 4.5, 6, 2), PINK)


def planning():
	a, b, c = rect(4, 6, 27, 10, 5), rect(13, 20, 33, 10, 5), rect(7, 34, 24, 10, 5)
	today = rect(26, 3, 4, 44, 2)
	icon = Icon().add(a, SKY).add(b, PURPLE).add(c, YELLOW)
	return icon.add(today, PINK).cross(a, today, NAVY).cross(b, today, WINE).cross(c, today, ORANGE)


def appraisal():
	left, right = rect(12, 26, 9, 21, 2, 22), rect(29, 26, 9, 21, 2, -22)
	medal = circle(25, 19, 15)
	star = path("M25 9.5l2.9 5.9 6.5.9-4.7 4.6 1.1 6.5-5.8-3.1-5.8 3.1 1.1-6.5-4.7-4.6 6.5-.9Z")
	icon = Icon().add(left, PURPLE).add(right, PINK).add(medal, YELLOW)
	return icon.cross(medal, left, BRICK).cross(medal, right, ORANGE).add(star, WHITE)


def social():
	cone = path("M8 18.5 33 7.5a2.5 2.5 0 0 1 3.5 2.3v28.4a2.5 2.5 0 0 1-3.5 2.3L8 31.5Z")
	mouth = rect(4, 17, 10, 16, 4)
	handle = rect(9, 29, 8, 16, 3, -12)
	icon = Icon().add(handle, PINK).add(cone, PURPLE).add(mouth, WINE)
	return icon.line("M41.5 18.5a8 8 0 0 1 0 13", TEAL, 3.5).line("M45 14a14 14 0 0 1 0 22", SKY, 3)


def marketing_automation():
	icon = Icon().line("M12 13h14a5 5 0 0 1 5 5v4M31 22v6a5 5 0 0 1-5 5h-1", PURPLE, 4)
	start, step, end = circle(11, 12, 7), rect(27, 15, 18, 14, 4), circle(18, 38, 8)
	icon.add(start, TEAL).add(step, YELLOW).add(end, PINK)
	return icon.add(path("M15.5 34.5 22 38l-6.5 3.5Z"), WHITE).add(rect(31, 20, 10, 4, 2), AMBER)


def approval():
	doc, badge = rect(6, 4, 28, 38, 5), circle(34, 34, 12)
	icon = two(doc, PURPLE, badge, TEAL, DEEP)
	for y in (12, 19, 26):
		icon.add(rect(12, y, 16, 3.5, 1.75), "#C78FB7")
	return icon.line("M28.5 34.5l4 4 7-8", WHITE, 3.5)


def whatsapp():
	big = path("M4 18A13 13 0 0 1 17 5h10a13 13 0 0 1 0 26H15l-8 6.5a1.6 1.6 0 0 1-2.6-1.3V18Z")
	small = path("M46 31a11 11 0 0 0-11-11h-6a11 11 0 0 0 0 22h9.5l5.8 4.5a1.3 1.3 0 0 0 2.2-1V31Z")
	icon = two(big, GREEN, small, TEAL, PINE)
	for x in (12.5, 19.5, 26.5):
		icon.add(circle(x, 18, 2.4), WHITE)
	return icon


def dealership():
	body = path("M4 30.5A4.5 4.5 0 0 1 8.5 26l5-8.3A5 5 0 0 1 17.8 15h12.4a5 5 0 0 1 3.9 1.9L41 26h.5a4.5 4.5 0 0 1 4.5 4.5V35a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3Z")
	glass = path("M17 26l3-6.5A2 2 0 0 1 21.9 18H29a2 2 0 0 1 1.6.8L36 26Z")
	icon = Icon().add(body, SKY).add(glass, BLUE)
	for x in (14, 36):
		icon.add(circle(x, 38, 6.5), INK).add(circle(x, 38, 2.5), GREY)
	return icon


def veron():
	"""ERP-VERON's V: two legs that meet at the bottom, over a yellow line"""
	left, right = rect(14, 3, 9, 38, 4.5, -17.9), rect(27, 3, 9, 38, 4.5, 17.9)
	return two(left, PURPLE, right, TEAL, DEEP)


# --- the modules that work behind the apps (the Apps page)

def core():
	return veron().add(rect(8, 40, 34, 3.5, 1.75), YELLOW).add(rect(14, 44.5, 22, 2.5, 1.25), PINK)


def account_iran():
	book, spine = rect(8, 4, 34, 42, 5), rect(8, 4, 9, 42, 4)
	icon = two(book, SKY, spine, BLUE, NAVY)
	return icon.add(rect(22, 12, 14, 4, 2), WHITE).add(rect(22, 20, 10, 4, 2), WHITE).add(circle(31, 34, 6), YELLOW)


def accounting():
	calc = rect(9, 4, 32, 42, 6)
	icon = Icon().add(calc, PURPLE).add(rect(14, 9, 22, 10, 3), TEAL)
	for i, (x, y) in enumerate([(14, 24), (22, 24), (30, 24), (14, 32), (22, 32), (30, 32)]):
		icon.add(rect(x, y, 6, 5, 1.5), YELLOW if i == 5 else "#C78FB7")
	return icon.add(rect(14, 39.5, 22, 2.5, 1.25), "#C78FB7")


def ai_agent_payroll():
	head = circle(18, 15, 9)
	body = path("M4 43c0-8.8 6.3-15 14-15s14 6.2 14 15a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3Z")
	spark = path("M37 16c1 4.6 3.4 7 8 8-4.6 1-7 3.4-8 8-1-4.6-3.4-7-8-8 4.6-1 7-3.4 8-8Z")
	icon = Icon().add(head, TEAL).add(body, TEAL).add(spark, PINK)
	return icon.cross(body, spark, PLUM)


def ai_agent_account():
	return petty_cash()


def apps():
	icon = Icon()
	for (x, y), c in zip([(5, 5), (27, 5), (5, 27)], (PURPLE, TEAL, YELLOW)):
		icon.add(rect(x, y, 18, 18, 5), c)
	return icon.add(circle(36, 36, 9.5), PINK)


def attendance_device():
	device = rect(10, 4, 30, 42, 6)
	icon = Icon().add(device, NAVY).add(rect(15, 9, 20, 9, 2.5), SKY)
	for r in (4, 7.5, 11):
		icon.line(f"M{25 - r} 33a{r} {r} 0 0 1 {2 * r} 0", TEAL, 2.4)
	return icon


def cheque():
	slip, stub = rect(4, 12, 42, 26, 4), rect(4, 12, 12, 26, 4)
	icon = two(slip, YELLOW, stub, PINK, ORANGE)
	icon.add(rect(21, 19, 18, 3.5, 1.75), AMBER).add(rect(21, 26, 11, 3.5, 1.75), AMBER)
	return icon.line("M32 32c2-3 4-3 5 0s3 3 5 0", WINE, 2.5)


def currency_rate():
	a, b = circle(18, 18, 13), circle(32, 32, 13)
	icon = two(a, YELLOW, b, TEAL, PINE)
	return icon.line("M10 39a12 12 0 0 0 7 5M40 11a12 12 0 0 0-7-5", PURPLE, 3)


def fonts_iran():
	"""A letter T, and the three dots of the Persian letters"""
	top, stem = rect(5, 6, 32, 9, 4), rect(16.5, 6, 9, 38, 4.5)
	icon = two(top, PURPLE, stem, PINK, WINE)
	return icon.add(circle(35.5, 34, 4.2), TEAL).add(circle(43.5, 34, 4.2), TEAL).add(circle(39.5, 26.5, 4.2), YELLOW)


def hr_iran():
	clock = circle(22, 25, 18)
	icon = Icon().add(clock, SKY).line("M22 15v10l7 5", WHITE, 3.5)
	pen = rect(33, 18, 8, 30, 2.5, 40)
	return icon.add(pen, YELLOW).cross(clock, pen, AMBER)


def hr_iran_lunch():
	bowl = path("M4 25h42a21 21 0 0 1-21 21A21 21 0 0 1 4 25Z")
	icon = Icon().line("M17 19c-2-3 2-5 0-9M25 19c-2-3 2-5 0-9M33 19c-2-3 2-5 0-9", GREY, 3)
	return icon.add(bowl, ORANGE).add(rect(4, 23, 42, 5, 2.5), YELLOW)


def migration():
	a, b = rect(4, 4, 22, 22, 5), rect(24, 24, 22, 22, 5)
	icon = Icon().add(a, GREY).add(b, PURPLE)
	return icon.line("M30 9h7a4 4 0 0 1 4 4v5M37.5 15l3.5 4 3.5-4M20 41h-7a4 4 0 0 1-4-4v-5", TEAL, 3.5)


def moadian():
	receipt = path("M9 7a3 3 0 0 1 3-3h26a3 3 0 0 1 3 3v37l-4-2.5-4 2.5-4-2.5-4 2.5-4-2.5-4 2.5-4-2.5L9 44Z")
	seal = circle(35, 35, 10)
	icon = two(receipt, SKY, seal, RED, NAVY)
	for y in (11, 18, 25):
		icon.add(rect(15, y, 18, 3.5, 1.75), WHITE)
	return icon.line("M31 35.5l3 3 5-6", WHITE, 3)


def pack_showroom():
	box = path("M25 4 45 13v24L25 46 5 37V13Z")
	icon = Icon().add(box, YELLOW).add(path("M25 22 45 13v24L25 46Z"), AMBER)
	return icon.add(path("M5 13 25 22 45 13 25 4Z"), PINK).add(path("M15 8.5 35 17.5v6l-4 1.8v-6L11 10.3Z"), WINE)


def payment_iran():
	back, front = rect(10, 6, 36, 24, 5, -8), rect(4, 17, 38, 25, 5)
	icon = two(back, PINK, front, PURPLE, PLUM)
	return icon.add(rect(4, 23, 38, 5, 0), INK).add(rect(9, 33, 11, 4, 2), YELLOW)


def planning_rotation():
	cal = rect(5, 8, 32, 32, 5)
	icon = Icon().add(cal, PURPLE).add(rect(5, 8, 32, 8, 4), PLUM)
	for x, y in ((10, 21), (18, 21), (26, 21), (10, 29)):
		icon.add(rect(x, y, 5, 4.5, 1.5), "#C78FB7")
	icon.add(circle(35, 35, 11), TEAL)
	return icon.line("M30 35a5 5 0 1 0 5-5h-2M33 27l3 3-3 3", WHITE, 2.6)


def sms_iran():
	phone = rect(9, 4, 22, 42, 5)
	bubble = path("M24 16a6 6 0 0 1 6-6h10a6 6 0 0 1 6 6v6a6 6 0 0 1-6 6h-7l-6 4.5V28a6 6 0 0 1-3-5.2Z")
	icon = Icon().add(phone, NAVY).add(rect(13, 9, 14, 28, 2), SKY).add(bubble, YELLOW).cross(phone, bubble, AMBER)
	return icon.add(rect(17, 40, 6, 2.5, 1.25), SKY)


def spreadsheet_iran():
	sheet = rect(4, 6, 42, 38, 5)
	icon = Icon().add(sheet, TEAL).add(rect(4, 6, 42, 9, 4), PINE)
	for x in (17, 30):
		icon.add(rect(x, 15, 2, 29, 0), PINE)
	return icon.add(rect(34, 26, 5, 13, 1.5), YELLOW).add(rect(22, 22, 5, 17, 1.5), PINK).add(rect(9, 30, 5, 9, 1.5), PURPLE)


def stock_kardex():
	icon = Icon()
	for (x, y), c in zip([(6, 26), (25, 26), (15, 7)], (YELLOW, AMBER, PINK)):
		icon.add(rect(x, y, 19 if x != 15 else 20, 18 if y != 7 else 17, 3), c)
	icon.add(rect(13, 32, 5, 3, 1.5), BRICK).add(rect(32, 32, 5, 3, 1.5), BRICK).add(rect(22.5, 12, 5, 3, 1.5), WINE)
	return icon


def storage_s3():
	cloud = path("M13 38a9 9 0 0 1-1.4-17.9A13 13 0 0 1 36.9 17 10.5 10.5 0 0 1 36.5 38Z")
	icon = Icon().add(cloud, SKY)
	for y in (24, 31):
		icon.add(rect(17, y, 16, 5, 2.5), BLUE)
	return icon.add(circle(29, 26.5, 1.2), WHITE).add(circle(29, 33.5, 1.2), WHITE)


def theme():
	sun, moon = circle(19, 25, 15), path("M33 10a15 15 0 1 1 0 30 11.5 11.5 0 0 0 0-30Z")
	icon = Icon().add(sun, YELLOW).add(moon, PURPLE)
	return icon.cross(sun, circle(36, 25, 15), PLUM)


def website_iran():
	globe = circle(25, 25, 21)
	icon = Icon().add(globe, BLUE).add(path("M25 4a21 21 0 0 1 0 42c-5-5-8-12-8-21s3-16 8-21Z"), SKY)
	return icon.line("M5.5 18h39M5.5 32h39", WHITE, 2.4).add(rect(23.7, 4, 2.6, 42, 1.3), WHITE)


def claude_provider():
	chip = rect(10, 10, 30, 30, 7)
	icon = Icon()
	for i in range(3):
		x = 17 + i * 8
		icon.add(rect(x - 1.5, 4, 3, 8, 1.5), GREY).add(rect(x - 1.5, 38, 3, 8, 1.5), GREY)
		icon.add(rect(4, x - 1.5, 8, 3, 1.5), GREY).add(rect(38, x - 1.5, 8, 3, 1.5), GREY)
	icon.add(chip, ORANGE)
	return icon.add(path("M25 15c1 5 4 9 10 10-6 1-9 5-10 10-1-5-4-9-10-10 6-1 9-5 10-10Z"), WHITE)


def veron_base():
	return veron().add(rect(13, 41.5, 24, 4.5, 2.25), YELLOW)


ICONS = {
	"veron_ai_agent": ai_agent, "veron_ai_agent_account": ai_agent_account, "veron_secretariat": secretariat,
	"veron_barcode": barcode, "veron_payroll_iran": payroll, "veron_shopfloor": shopfloor, "veron_plm": plm,
	"veron_rental": rental, "veron_planning": planning, "veron_appraisal": appraisal, "veron_social": social,
	"veron_marketing_automation": marketing_automation, "veron_approval": approval, "veron_whatsapp": whatsapp,
	"veron_dealership": dealership, "veron_base": veron_base, "veron_core": core, "veron_account_iran": account_iran,
	"veron_accounting": accounting, "veron_ai_agent_payroll": ai_agent_payroll, "veron_apps": apps,
	"veron_attendance_device": attendance_device, "veron_cheque": cheque, "veron_currency_rate": currency_rate,
	"veron_fonts_iran": fonts_iran, "veron_hr_iran": hr_iran, "veron_hr_iran_lunch": hr_iran_lunch,
	"veron_migration": migration, "veron_moadian": moadian, "veron_pack_showroom": pack_showroom,
	"veron_payment_iran": payment_iran, "veron_planning_rotation": planning_rotation, "veron_sms_iran": sms_iran,
	"veron_spreadsheet_iran": spreadsheet_iran, "veron_stock_kardex": stock_kardex, "veron_storage_s3": storage_s3,
	"veron_theme": theme, "veron_website_iran": website_iran, "ai_claude_anthropic": claude_provider,
}


def main(out=None):
	for module, draw in sorted(ICONS.items()):
		folder = os.path.join(out or ROOT, module, "static", "description") if not out else out
		if not out and not os.path.isdir(os.path.join(ROOT, module)):
			continue
		os.makedirs(folder, exist_ok=True)
		name = "icon.svg" if not out else f"{module}.svg"
		with open(os.path.join(folder, name), "w") as f:
			f.write(draw().svg())
	print(len(ICONS), "icons")


if __name__ == "__main__":
	main(sys.argv[1] if len(sys.argv) > 1 else None)
