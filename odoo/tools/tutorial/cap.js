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
  async snap(name) {
    // the picture taken from the browser's own surface: Playwright's screenshot came out blank on some pages
    // (the email editor), the browser's capture does not
    try {
      this.cdp = this.cdp || await this.page.context().newCDPSession(this.page);
      const shot = await this.cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true });
      fs.writeFileSync(path.join(this.out, name), Buffer.from(shot.data, 'base64'));
    } catch (e) {
      await this.page.screenshot({ path: path.join(this.out, name) });
    }
    return name;
  }
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
    const b = await l.boundingBox({ timeout: 5000 }).catch(() => null);
    return b ? [b.x, b.y, b.width, b.height] : null;
  }
  // a thing above or below what shows: the page scrolls to it smoothly (never a jump the viewer cannot follow)
  async reveal(sel, opts = {}) {
    if (sel === undefined || sel === null || (Array.isArray(sel) && typeof sel[0] === 'number')) return;
    if (Array.isArray(sel)) sel = sel[0];
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    // the bar of menus, the control panel, a menu, a dialog: they do not scroll with the page
    const fixed = await l.evaluate((e) => !!e.closest('.o_main_navbar, .o_control_panel, .o-dropdown--menu, .modal, .o_popover, .o-autocomplete--dropdown-menu, .o-overlay-container')).catch(() => true);
    if (fixed) return;
    const out = (b) => !b || b.y < 40 || b.y + Math.min(b.height, VH * 0.6) > VH - 24;
    let b = await l.boundingBox({ timeout: 4000 }).catch(() => null);
    if (b && out(b)) {
      const dy = Math.round(b.y + Math.min(b.height, VH * 0.6) / 2 - VH * 0.45);
      const x = Math.min(VW - 40, Math.max(40, b.x + Math.min(b.width, 200) / 2));
      const sub = this.sub, step = this.step;
      await this.scroll(dy, { at: [x, VH / 2], dur: Math.min(2.2, 0.7 + Math.abs(dy) / 600), hold: 0.2, sub: opts.sub, step: opts.step });
      const after = await l.boundingBox({ timeout: 2000 }).catch(() => null);
      if (after && Math.abs(after.y - b.y) < 4) {
        // nothing moved: the scroll is taken back
        const rec = this.steps.pop(); this.n--; this.sub = sub; this.step = step;
        for (const f of [rec.file, ...rec.files]) fs.unlinkSync(path.join(this.out, f));
      }
      b = after;
    }
    if (!b || out(b)) await l.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
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
    if (opts.focus) await this.reveal(opts.focus, opts);
    const cam = opts.focus ? { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom } : undefined;
    const rec = { kind: 'view', file: await this.snap(this.file()) };
    if (cam) rec.cam = cam;
    this.push(rec, opts);
  }
  // the cursor goes to a thing and clicks it; then the page as it becomes
  async click(sel, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    await this.reveal(l, opts);
    const target = await this.box(l);
    const cam = opts.focus ? { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom } : undefined;
    const rec = { kind: 'click', file: await this.snap(this.file()), target };
    if (cam) rec.cam = cam;
    this.push(rec, { ...opts, newpage: undefined, done: undefined });
    if (opts.dbl) await l.dblclick({ timeout: 8000 }); else await l.click({ timeout: 8000 });
    if (opts.after !== false) {
      const v = { wait: opts.wait ?? 700, newpage: opts.newpage, hold: opts.afterHold ?? 1.0, done: opts.done, sub: opts.afterSub };
      if (opts.afterCam && opts.afterCam.focus) { v.focus = opts.afterCam.focus; v.zoom = opts.afterCam.zoom; }
      else if (opts.afterCam) v.cam = opts.afterCam;
      await this.view(v);
    }
  }
  async hover(sel, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    await this.reveal(l, opts);
    const target = await this.box(l);
    const cam = opts.focus ? { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom } : undefined;
    await l.hover();
    await this.page.waitForTimeout(400);
    const rec = { kind: 'hover', file: await this.snap(this.file()), target };
    if (cam) rec.cam = cam;
    this.push(rec, opts);
  }
  // typing into a field: one picture every few letters
  async type(sel, text, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    await this.reveal(l, opts);
    const target = await this.box(l);
    let cam = opts.focus ? { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom } : undefined;
    if (!cam && opts.cam === undefined && target) {
      // a field of a form: the camera keeps the whole width of the form's sheet (its labels and the other column
      // with it) and only follows the field up and down, never off to one side
      const sheet = await l.evaluate((e) => { const s = e.closest('.o_form_sheet'); if (!s) return null;
        const b = s.getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; }).catch(() => null);
      if (sheet && !(await l.evaluate((e) => !!e.closest('.o_list_renderer, .modal')).catch(() => false)))
        cam = { focus: [sheet[0], target[1] - 170, sheet[2], target[3] + 340] };
    }
    const first = await this.snap(this.file());
    if (opts.line) {
      // a text of a page being edited: the line chosen with three clicks and typed over (Ctrl+A would take the page)
      await l.click({ timeout: 8000, clickCount: 3 });
      await this.page.waitForTimeout(250);
    } else {
      await l.click({ timeout: 8000 });
      if (opts.clear !== false) { await this.page.keyboard.press('Control+A'); await this.page.keyboard.press('Delete'); }
    }
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
    if (cam) rec.cam = cam;
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
  // a file chosen from the computer: the cursor clicks the button, the computer's window for opening a file shows
  // (drawn in the page, as the screenshots cannot see the real one), the file is picked and opened
  async chooseFile(sel, file, opts = {}) {
    const l = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    await this.reveal(l, opts);
    const target = await this.box(l);
    this.push({ kind: 'click', file: await this.snap(this.file()), target, mark: true }, { sub: opts.sub, step: opts.step });
    const [chooser] = await Promise.all([this.page.waitForEvent('filechooser', { timeout: 8000 }), l.click()]);
    const name = path.basename(file);
    await this.page.evaluate(({ name, others }) => {
      const icon = (n) => n.endsWith('.xlsx') ? '#1f9d55' : n.endsWith('.pdf') ? '#d64541' : n.endsWith('.docx') ? '#2b6cd4' : '#8a8f99';
      const rows = [...others, name].sort().map((n) => `<div class="fd-row" data-n="${n}"><span class="fd-ic" style="background:${icon(n)}"></span><span>${n}</span><span class="fd-d">۱۴۰۵/۰۸/۲۱</span></div>`).join('');
      const d = document.createElement('div');
      d.id = 'fd';
      d.innerHTML = `<style>
        #fd{position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;font-family:Vazirmatn,sans-serif;direction:rtl}
        #fd .fd-w{width:720px;background:#202127;border:1px solid #3a3b44;border-radius:10px;box-shadow:0 24px 60px rgba(0,0,0,.6);color:#e6e7ea;overflow:hidden}
        #fd .fd-t{padding:12px 16px;background:#2a2b33;font-weight:700;font-size:15px;border-bottom:1px solid #3a3b44}
        #fd .fd-b{display:flex;height:300px} #fd .fd-s{width:170px;border-left:1px solid #3a3b44;padding:10px;font-size:14px;color:#b8bac2}
        #fd .fd-s div{padding:7px 10px;border-radius:6px} #fd .fd-s .on{background:#34353f;color:#fff}
        #fd .fd-l{flex:1;padding:8px} #fd .fd-row{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:6px;font-size:14px;direction:ltr;justify-content:flex-end}
        #fd .fd-row.sel{background:#3b2a33;outline:1px solid #c8202b} #fd .fd-ic{width:18px;height:22px;border-radius:3px;order:3}
        #fd .fd-d{color:#8d8f99;font-size:12px;margin-right:auto;order:0} #fd .fd-row span:nth-child(2){order:2}
        #fd .fd-f{display:flex;gap:10px;align-items:center;padding:12px 16px;border-top:1px solid #3a3b44;background:#25262d}
        #fd .fd-n{flex:1;background:#18191d;border:1px solid #3a3b44;border-radius:6px;padding:7px 10px;direction:ltr;text-align:right;min-height:20px;font-size:14px}
        #fd button{border:0;border-radius:6px;padding:8px 18px;font:600 14px Vazirmatn,sans-serif;cursor:pointer}
        #fd .fd-o{background:#c8202b;color:#fff} #fd .fd-c{background:#34353f;color:#ddd}</style>
        <div class="fd-w"><div class="fd-t">باز کردن فایل</div><div class="fd-b"><div class="fd-s"><div>دسکتاپ</div><div class="on">اسناد</div><div>دانلودها</div></div>
        <div class="fd-l">${rows}</div></div><div class="fd-f"><div class="fd-n"></div><button class="fd-c">انصراف</button><button class="fd-o">باز کردن</button></div></div>`;
      document.body.appendChild(d);
      d.querySelectorAll('.fd-row').forEach((r) => r.addEventListener('click', () => {
        d.querySelectorAll('.fd-row').forEach((x) => x.classList.remove('sel')); r.classList.add('sel');
        d.querySelector('.fd-n').textContent = r.dataset.n; }));
      d.querySelector('.fd-o').addEventListener('click', () => d.remove());
    }, { name, others: opts.others || [] });
    const win = { focus: '#fd .fd-w', zoom: 1.35 };
    await this.view({ wait: 300, hold: 0.8, sub: opts.dialogSub, ...win });
    await this.click(this.page.locator(`#fd .fd-row[data-n="${name}"]`), { wait: 300, afterHold: 0.6, ...win, afterCam: win });
    await this.click(this.page.locator('#fd .fd-o'), { wait: 100, after: false, ...win });
    await chooser.setFiles(file);
    await this.view({ wait: opts.wait ?? 2500, newpage: true, hold: opts.afterHold ?? 1.6, sub: opts.afterSub, done: opts.done });
  }
  // a thing dragged and dropped: the cursor takes it, carries it and lets it go
  async drag(src, dst, opts = {}) {
    const a = await this.box(src), b = Array.isArray(dst) ? dst : await this.box(dst);
    this.push({ kind: 'hover', file: await this.snap(this.file()), target: a, mark: true }, { ...opts, hold: 0.6 });
    const ax = a[0] + a[2] / 2, ay = a[1] + a[3] / 2, bx = b[0] + b[2] / 2, by = b[1] + b[3] / 2;
    await this.page.mouse.move(ax, ay);
    await this.page.mouse.down();
    for (let i = 1; i <= 18; i++) { await this.page.mouse.move(ax + (bx - ax) * i / 18, ay + (by - ay) * i / 18); await this.page.waitForTimeout(35); }
    await this.page.waitForTimeout(400);
    this.push({ kind: 'click', file: await this.snap(this.file()), target: b }, { hold: 0.2 });
    await this.page.mouse.up();
    await this.view({ wait: opts.wait ?? 2500, hold: opts.afterHold ?? 1.0, cam: opts.afterCam });
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
  // every section starts on the apps page: the app is opened from its icon, never by an address the viewer did not see
  async openApp(xmlid, opts = {}) {
    await this.page.goto(B + '/odoo');
    await this.settle(1200);
    await this.view({ sub: opts.sub, step: opts.step ?? 0, hold: 1.2, newpage: true, cam: 'full' });
    const icon = this.page.locator(`.o-app-menu-item[data-menu-xmlid="${xmlid}"]`).first();
    const b = await icon.boundingBox({ timeout: 5000 }).catch(() => null);
    if (b && b.y + b.height > VH - 40) {
      // the icon low on the page: it goes down until the icon and its name show whole
      await this.scroll(Math.round(b.y + b.height - (VH - 150)), { at: [40, 420], dur: 1.3, hold: 0.4 });
    }
    await this.click(icon, { wait: 1800, newpage: true, afterHold: opts.hold ?? 1.4, afterSub: opts.afterSub });
  }
  // the menus of the app, one after another, each opened and told about, before the work starts
  async tourMenus(items, opts = {}) {
    const bar = ['.o_menu_brand', '.o_menu_sections'];
    for (const [k, [t, sub]] of items.entries()) {
      await this.click(this.topMenu(t), { sub, step: k === 0 ? opts.step : undefined, wait: 600, afterHold: 1.4, focus: bar, zoom: 1.3,
        afterCam: { focus: ['.o_menu_sections', '.o-dropdown--menu'], zoom: 1.3 } });
      await this.page.keyboard.press('Escape');
      await this.page.waitForTimeout(350);
    }
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
      await this.reveal(sel, opts);
      const target = await this.box(sel);
      const cam = opts.focus ? { focus: await this.box(opts.focus) ?? opts.focus, zoom: opts.zoom } : undefined;
      const rec = { kind: 'click', file: await this.snap(this.file()), target };
      if (cam) rec.cam = cam;
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
