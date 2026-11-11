const { chromium } = require('playwright');
const path = require('path'), fs = require('fs');
const [scene, ...times] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  p.on('pageerror', e => console.log('ERR', e.message)); p.on('console', m => m.type() === 'error' && console.log('CONSOLE', m.text()));
  await p.goto('file://' + path.join(__dirname, 'intro.html')); await p.evaluate(() => window.ready);
  for (const t of times) {
    const url = await p.evaluate(([t, s]) => { render(+t, s); return document.getElementById('c').toDataURL('image/png'); }, [t, scene]);
    fs.writeFileSync(path.join(__dirname, `st_${scene}_${t}.png`), Buffer.from(url.split(',')[1], 'base64'));
  }
  await b.close();
})();
