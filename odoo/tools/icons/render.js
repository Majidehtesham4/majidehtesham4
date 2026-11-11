// icon.png (256 x 256, transparent) of every module from its icon.svg; see make_icons.py
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..', '..', 'addons');
(async () => {
	const browser = await chromium.launch();
	const page = await browser.newPage({ viewport: { width: 256, height: 256 } });
	let count = 0;
	for (const module of fs.readdirSync(root).sort()) {
		const svg = path.join(root, module, 'static', 'description', 'icon.svg');
		if (!fs.existsSync(svg)) continue;
		const data = fs.readFileSync(svg).toString('base64');
		await page.setContent(`<html><body style="margin:0;background:transparent"><img style="width:256px;height:256px;display:block" src="data:image/svg+xml;base64,${data}"></body></html>`);
		await page.waitForTimeout(50);
		await page.screenshot({ path: path.join(root, module, 'static', 'description', 'icon.png'), omitBackground: true });
		count++;
	}
	await browser.close();
	console.log(count, 'icons');
})();
