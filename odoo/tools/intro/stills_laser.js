const { chromium } = require('playwright');
const path = require('path'), fs = require('fs');
const times = process.argv.slice(2);
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  p.on('pageerror', e => console.log('ERR', e.message)); p.on('console', m => (m.type() === 'error' || m.type() === 'warning') && console.log('CONSOLE', m.text().slice(0, 300)));
  await p.goto('http://127.0.0.1:8765/laser.html'); await p.waitForFunction(() => window.ready, null, { timeout: 60000 }); await p.evaluate(() => window.ready);
  for (const t of times) {
    const t0 = Date.now();
    const url = await p.evaluate((t) => { render(+t); return document.querySelector('canvas').toDataURL('image/png'); }, t);
    fs.writeFileSync(path.join(__dirname, `st_${t}.png`), Buffer.from(url.split(',')[1], 'base64'));
    console.log(t, (Date.now() - t0) + 'ms');
  }
  await b.close();
})();
