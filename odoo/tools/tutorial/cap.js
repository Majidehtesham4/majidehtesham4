// Records a section: the program is driven in a browser and, at each step, a screenshot, where the cursor goes,
// what the subtitle says and which step of the panel it is (steps.json). compose.py turns it into the film.
//   node cap.js <section> <out folder>      (sections/sNN.js; the program on localhost:8069, database aryapack)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const B = process.env.BASE || 'http://localhost:8069';
const DB = process.env.DB || 'aryapack';
const VW = 1440, VH = 810;

class Recorder {
  constructor(page, out) {
    this.page = page; this.out = out; this.steps = []; this.n = 0; this.sub = ''; this.step = 0;
  }
  file(suffix = '') { return String(this.n).padStart(3, '0') + suffix + '.png'; }
  async settle(ms = 500) {
    await this.page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    await this.page.waitForTimeout(ms);
  }
  async snap(name) { await this.page.screenshot({ path: path.join(this.out, name) }); return name; }
  async box(sel) {
    // a rectangle as it is; several things: the rectangle around them all
    if (Array.isArray(sel) && typeof sel[0] === 'number') return sel;
    if (Array.isArray(sel)) {
      const bs = (await Promise.all(sel.map((s) => this.box(s)))).filter(Boolean);
      if (!bs.length) return null;
      const x0 = Math.min(...bs.map((b) => b[0])), y0 = Math.min(...bs.map((b) => b[1]));
      const x1 = Math.max(...bs.map((b) => b[0] + b[2])), y1 = Math.max(...bs.map((b) => b[1] + b[3]));
      return [x0, y0, x1 - x0, y1 - y0];
    }
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    await l.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
    const b = await l.boundingBox({ timeout: 5000 }).catch(() => null);
    return b ? [b.x, b.y, b.width, b.height] : null;
  }
  url() { return this.page.url().replace(/^https?:\/\/[^/]+/, 'aryapack.veronerp.ir'); }
  push(rec, opts) {
    if (opts.sub !== undefined) this.sub = opts.sub;
    if (opts.step !== undefined) this.step = opts.step;
    rec.sub = this.sub; rec.step = this.step;
    for (const k of ['hold', 'cam', 'done', 'newpage', 'mark']) if (opts[k] !== undefined) rec[k] = opts[k];
    if (!('url' in rec)) rec.url = this.url();
    this.steps.push(rec); this.n++;
    console.log(this.n, rec.kind, rec.sub.slice(0, 50));
  }
  // a look at the page as it is
  async view(opts = {}) {
    await this.settle(opts.wait ?? 400);
    const rec = { kind: 'view', file: await this.snap(this.file()) };
    if (opts.focus) rec.cam = { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom };
    this.push(rec, opts);
  }
  // the cursor goes to a thing and clicks it; then the page as it becomes
  async click(sel, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    const target = await this.box(l);
    const rec = { kind: 'click', file: await this.snap(this.file()), target };
    if (opts.focus) rec.cam = { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom };
    this.push(rec, { ...opts, newpage: undefined, done: undefined });
    await l.click({ timeout: 8000 });
    if (opts.after !== false) {
      const v = { wait: opts.wait ?? 700, newpage: opts.newpage, hold: opts.afterHold ?? 1.0, done: opts.done };
      if (opts.afterCam && opts.afterCam.focus) { v.focus = opts.afterCam.focus; v.zoom = opts.afterCam.zoom; }
      else if (opts.afterCam) v.cam = opts.afterCam;
      await this.view(v);
    }
  }
  async hover(sel, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    const b = await l.boundingBox({ timeout: 5000 }).catch(() => null);
    const target = b ? [b.x, b.y, b.width, b.height] : null;
    await l.hover();
    await this.page.waitForTimeout(400);
    const rec = { kind: 'hover', file: await this.snap(this.file()), target };
    if (opts.focus) rec.cam = { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom };
    this.push(rec, opts);
  }
  // typing into a field: one picture every few letters
  async type(sel, text, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    const target = await this.box(l);
    const first = await this.snap(this.file());
    await l.click({ timeout: 8000 });
    if (opts.clear !== false) { await this.page.keyboard.press('Control+A'); await this.page.keyboard.press('Delete'); }
    const files = [];
    const every = text.length > 24 ? 3 : text.length > 12 ? 2 : 1;
    for (let i = 0; i < text.length; i++) {
      await this.page.keyboard.type(text[i], { delay: 10 });
      if ((i + 1) % every === 0 || i === text.length - 1) {
        await this.page.waitForTimeout(60);
        files.push(await this.snap(this.file('_t' + String(files.length).padStart(3, '0'))));
      }
    }
    const rec = { kind: 'type', file: first, files, target };
    if (opts.focus) rec.cam = { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom };
    else if (opts.cam !== undefined) rec.cam = opts.cam;
    this.push(rec, opts);
    if (opts.enter) { await this.page.keyboard.press('Enter'); }
    if (opts.pick) {
      // an autocomplete: its list shows, the first match is chosen
      await this.page.waitForSelector('.o-autocomplete--dropdown-item', { timeout: 8000 });
      await this.page.waitForTimeout(500);
      await this.click(this.page.locator('.o-autocomplete--dropdown-item', { hasText: opts.pick }).first(), { sub: opts.pickSub, wait: 600, afterHold: 0.6 });
    } else if (opts.after) {
      await this.view({ wait: 500, hold: 0.8 });
    }
  }
  // the page scrolled smoothly by dy css px (the wheel, where the pointer is), a picture every few px
  async scroll(dy, opts = {}) {
    const at = opts.at || [40, 420];
    await this.page.mouse.move(at[0], at[1]);
    const first = await this.snap(this.file());
    const files = [];
    const n = Math.max(6, Math.round(Math.abs(dy) / 18));
    for (let i = 0; i < n; i++) {
      await this.page.mouse.wheel(0, dy / n);
      await this.page.waitForTimeout(40);
      files.push(await this.snap(this.file('_t' + String(files.length).padStart(3, '0'))));
    }
    await this.page.waitForTimeout(300);
    this.push({ kind: 'scroll', file: first, files, dur: opts.dur ?? 2.2 }, opts);
  }
  // the address of the program typed in the browser's bar
  async address(text, go, opts = {}) {
    const blank = await this.snap(this.file());
    this.push({ kind: 'url', file: blank, url_typed: text, url: '' }, opts);
    await this.page.goto(go);
    await this.settle(800);
  }
  async goto(url, opts = {}) {
    await this.page.goto(B + url);
    await this.settle(opts.wait ?? 900);
    if (opts.view !== false) await this.view({ ...opts, newpage: true });
  }
  async login(user, pass) {
    await this.page.goto(B + '/web/login?db=' + DB);
    await this.page.fill('input[name=login]', user);
    await this.page.fill('input[name=password]', pass);
    await this.page.click('.oe_login_form button[type=submit]');
    await this.settle(1500);
  }
  // shortcuts for the forms of the program
  topMenu(t) { return this.page.locator('.o_menu_sections button, .o_menu_sections a', { hasText: t }).first(); }
  menuItem(t) { return this.page.locator('.o-dropdown--menu .dropdown-item, .o-dropdown--menu .o-dropdown-item', { hasText: t }).first(); }
  async menu(top, item, opts = {}) {
    await this.click(this.topMenu(top), { ...opts, wait: 600, afterHold: 0.5, afterCam: { focus: [500, 0, 940, 300], zoom: 1.3 } });
    if (item) await this.click(this.menuItem(item), { wait: 1500, newpage: true, afterHold: 0.8 });
  }
  field(name) { return this.page.locator(`div[name=${name}] input, div[name=${name}] textarea`).first(); }
  async set(name, value, opts = {}) { await this.type(this.field(name), String(value), opts); }
  async many2one(name, text, opts = {}) {
    await this.type(this.field(name), text, { ...opts, pick: opts.pick || text, pickSub: opts.pickSub });
  }
  async saveForm(opts = {}) { await this.click('.o_form_button_save', { wait: 1500, afterHold: 1.0, ...opts }); }
  async create(opts = {}) {
    await this.click('.o_list_button_add, .o-kanban-button-new, .o_form_button_create', { wait: 1500, newpage: true, afterHold: 0.6, ...opts });
  }
  async select(name, label, opts = {}) {
    // a selection: a <select>, radio buttons, or the menu of a select field
    const div = this.page.locator(`div[name=${name}]`).first();
    const sel = div.locator('select');
    const radio = div.locator('.o_radio_item, .form-check', { hasText: label }).first();
    if (await sel.count()) {
      const target = await this.box(sel);
      const rec = { kind: 'click', file: await this.snap(this.file()), target };
      if (opts.focus) rec.cam = { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom };
      this.push(rec, { ...opts, done: undefined });
      await sel.selectOption({ label });
      await this.view({ wait: 700, hold: opts.afterHold ?? 0.9, done: opts.done });
    } else if (await radio.count()) {
      await this.click(radio.locator('input, label').first(), { ...opts, wait: 700, afterHold: opts.afterHold ?? 0.9 });
    } else {
      await this.click(div.locator('input, .o_select_menu_toggler').first(), { ...opts, done: undefined, wait: 600, afterHold: 0.6 });
      await this.click(this.page.locator('.o_select_menu_item, .o-dropdown--menu .dropdown-item', { hasText: label }).first(),
        { wait: 700, afterHold: opts.afterHold ?? 0.9, done: opts.done });
    }
  }
  async search(text, opts = {}) {
    await this.type('.o_searchview_input', text, { ...opts, enter: true });
    await this.view({ wait: 1200, hold: opts.afterHold ?? 1.4, done: opts.done });
  }
  async button(text, opts = {}) {
    await this.click(this.page.locator('button:visible', { hasText: text }).first(), { wait: 1500, afterHold: 1.0, ...opts });
  }
  save() { fs.writeFileSync(path.join(this.out, 'steps.json'), JSON.stringify(this.steps, null, 1)); }
}

(async () => {
  const [section, out] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  for (const f of fs.readdirSync(out)) if (f.endsWith('.png')) fs.unlinkSync(path.join(out, f));
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, deviceScaleFactor: 2, locale: 'fa-IR', timezoneId: 'Asia/Tehran' });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('PAGE ERROR', e.message));
  await page.addInitScript(() => {
    let css = '*{caret-color:transparent!important} .o_notification_manager{display:none!important}';
    // the sign-in page without the website's header and footer (they are set up in section 12), dark like the program
    if (location.pathname.startsWith('/web/login')) css += ' header#top,footer#bottom,.o_footer{display:none!important}'
      + ' html,body,#wrapwrap,main{background:#141418!important} #wrapwrap{min-height:100vh} main{padding-top:150px}'
      + ' .oe_website_login_container{max-width:380px;margin:0 auto;padding:34px 32px 26px;background:#1d1e24;border:1px solid #2f3038;border-radius:16px;box-shadow:0 20px 50px rgba(0,0,0,.5)}'
      + ' .oe_website_login_container:before{content:"ERP-VERON";display:block;text-align:center;font:700 26px Vazirmatn,sans-serif;color:#fff;margin-bottom:18px;letter-spacing:1px}'
      + ' .oe_login_form label,.oe_login_form .form-label{color:#d8d9de!important} .oe_login_form .form-control{background:#25262d!important;color:#eee!important;border-color:#3b3c45!important}'
      + ' .oe_login_form .btn-primary{background:#c8202b!important;border-color:#c8202b!important} .oe_login_form a,.oe_login_form .text-muted,.o_login_auth{color:#9a9ba4!important}'
      + ' .oe_login_form .input-group .btn{background:#25262d!important;border-color:#3b3c45!important;color:#ccc!important}';
    document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s); });
  });
  const R = new Recorder(page, out);
  R.B = B; R.DB = DB;
  try {
    await require(path.join(__dirname, 'sections', `s${String(section).padStart(2, '0')}.js`))(R, page);
  } finally {
    R.save();
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
