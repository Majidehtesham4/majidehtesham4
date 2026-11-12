"""A flat illustration of a vertical packaging machine (VFFS) for the shop's sample product: drawn, not a photo
	python3 make_machine.py  ->  vffs320.png"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 4
W = H = 900
im = Image.new("RGBA", (W * S, H * S), (244, 245, 247, 255))
d = ImageDraw.Draw(im)


def r(box, fill, rad=0, outline=None, width=0):
	box = [v * S for v in box]
	d.rounded_rectangle(box, rad * S, fill=fill, outline=outline, width=width * S)


steel, steel_d, steel_l = (196, 201, 208), (150, 156, 165), (224, 227, 231)
red, dark = (200, 32, 43), (38, 40, 46)
# the floor shadow
sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
ImageDraw.Draw(sh).ellipse([180 * S, 800 * S, 720 * S, 850 * S], fill=(0, 0, 0, 70))
im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14 * S)))
# the frame and the body
r([250, 300, 650, 790], steel, 10, steel_d, 3)
r([262, 312, 638, 778], steel_l, 8)
for x in (250, 632):
	r([x, 300, x + 18, 812], steel_d, 4)
# the hopper and the film roll
d.polygon([(330 * S, 70 * S), (570 * S, 70 * S), (500 * S, 200 * S), (400 * S, 200 * S)], fill=steel, outline=steel_d, width=3 * S)
r([400, 200, 500, 240], steel_d, 4)
r([660, 360, 760, 460], (228, 230, 234), 50, steel_d, 3)
r([695, 395, 725, 425], steel_d, 15)
d.line([(700 * S, 410 * S), (520 * S, 330 * S)], fill=(170, 175, 182), width=4 * S)
# the forming tube and the sealing jaws
r([420, 240, 480, 560], (210, 214, 220), 6, steel_d, 2)
r([360, 470, 418, 520], red, 6)
r([482, 470, 540, 520], red, 6)
# the bags
for k, y in enumerate((600, 660)):
	r([400, y, 500, y + 52], (232, 180, 60) if k else (240, 196, 80), 8, (190, 140, 40), 2)
r([300, 730, 600, 760], dark, 6)
# the control panel
r([140, 330, 240, 520], dark, 10)
r([152, 344, 228, 410], (40, 110, 160), 6)
for i, c in enumerate(((60, 200, 90), (230, 180, 40), red)):
	d.ellipse([(160 + i * 24) * S, 440 * S, (176 + i * 24) * S, 456 * S], fill=c)
r([160, 475, 220, 500], (70, 72, 80), 4)
d.line([(240 * S, 420 * S), (262 * S, 420 * S)], fill=dark, width=6 * S)
# the model's name
d.text((285 * S, 330 * S), "VFFS-320", fill=red, font=ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Medium.otf", 30 * S))
im = im.resize((W, H), Image.LANCZOS).convert("RGB")
im.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vffs320.png"))
