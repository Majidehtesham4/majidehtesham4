"""The wordmark's mask from the designed image (dark letters on white, a red line under ERP):
python3 wordmark.py VERON-ERP.jpg  ->  wordmark_mask.png and wordmark_mask.js (the mask inlined, so the page can use it)"""
import base64
import sys

import numpy as np
from PIL import Image

im = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(float)
r, g, b = im[..., 0], im[..., 1], im[..., 2]
alpha = np.clip((235 - (0.299 * r + 0.587 * g + 0.114 * b)) / 210, 0, 1)
alpha[r - g > 40] = 0  # the red line is drawn as light, not traced
x0, y0, x1, y1 = 140, 80, 1895, 370  # the letters of the 2000 x 429 design
out = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
out[..., :3] = 255
out[..., 3] = (alpha[y0:y1, x0:x1] * 255).round()
Image.fromarray(out, "RGBA").save("wordmark_mask.png")
data = base64.b64encode(open("wordmark_mask.png", "rb").read()).decode()
with open("wordmark_mask.js", "w") as f:
	f.write("// The wordmark VERON ERP as an alpha mask (traced from the designed image); made by wordmark.py\n")
	f.write(f'window.WORDMARK_MASK = "data:image/png;base64,{data}";\n')
