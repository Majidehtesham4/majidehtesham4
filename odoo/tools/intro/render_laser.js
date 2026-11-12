// The laser intro, frame by frame into ffmpeg: 24 frames a second, each the mean of two moments half a frame
// apart (a 180-degree shutter: motion blur, as a film camera has)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const [out, fpsArg, from, to] = process.argv.slice(2);
const fps = +(fpsArg || 24);
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  p.on('pageerror', e => console.log('ERR', e.message));
  await p.goto('http://127.0.0.1:8765/laser.html'); await p.waitForFunction(() => window.ready); await p.evaluate(() => window.ready);
  await p.evaluate(() => {
    const acc = document.createElement('canvas'); acc.width = 1920; acc.height = 1080; window.ACC = acc.getContext('2d');
    window.frame = (t, dt) => {
      const gl = document.querySelector('canvas');
      render(t); ACC.globalAlpha = 1; ACC.drawImage(gl, 0, 0);
      render(t + dt); ACC.globalAlpha = 0.5; ACC.drawImage(gl, 0, 0);
      return ACC.canvas.toDataURL('image/png');
    };
  });
  const len = await p.evaluate(() => window.LEN);
  const n = Math.round(len * fps), a = +(from || 0), z = Math.min(n, +(to || n));
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-tune', 'grain', '-x264-params', 'aq-mode=3', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let i = a; i < z; i++) {
    const url = await p.evaluate(([t, dt]) => window.frame(t, dt), [i / fps, 0.5 / fps]);
    if (!ff.stdin.write(Buffer.from(url.split(',')[1], 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 24 === 0) console.log(`frame ${i}/${z}`);
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r)); await b.close();
})();
