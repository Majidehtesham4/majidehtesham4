const { chromium } = require('playwright');
const fs = require('fs');
const D = process.argv[2];
const B = 'http://localhost:8069';
const shots = [];
let page;
async function box(sel) {
  const l = typeof sel === 'string' ? page.locator(sel).first() : sel;
  const b = await l.boundingBox({ timeout: 2000 }).catch(() => null);
  return b ? [b.x, b.y, b.width, b.height] : null;
}
async function shot(name, boxes = {}, opts = {}) {
  await page.waitForTimeout(opts.wait ?? 350);
  const out = {};
  for (const [k, s] of Object.entries(boxes)) out[k] = await box(s);
  const file = name + '.png';
  await page.screenshot({ path: D + '/' + file, fullPage: !!opts.full });
  const size = opts.full ? await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight]) : [1920, 1080];
  shots.push({ name, file, size, boxes: out });
  console.log('shot', name, JSON.stringify(out));
}
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, locale: 'fa-IR' });
  page = await ctx.newPage();
  await page.goto(B + '/web/login?db=vid');
  await page.fill('input[name=login]', 'admin'); await page.fill('input[name=password]', 'admin');
  await page.click('button[type=submit]'); await page.waitForTimeout(2500);
  // no blinking caret, no notifications
  await page.addStyleTag({ content: '*{caret-color:transparent!important} .o_notification_manager{display:none!important}' });

  await page.goto(B + '/odoo/accounting'); await page.waitForSelector('.o_kanban_record'); await page.waitForTimeout(1500);
  await shot('dash', { sales: page.locator('.o_kanban_record').first(), unpaid: page.locator('.o_kanban_record').first().locator('a', { hasText: 'پرداخت نشده' }), menu: '.o_menu_sections' });

  await page.goto(B + '/odoo/action-account.action_move_out_invoice_type'); await page.waitForSelector('.o_data_row'); await page.waitForTimeout(1200);
  await shot('list', { new: '.o_list_button_add', rows: '.o_list_table tbody', first: '.o_data_row', total: '.o_list_table tfoot' });

  await page.click('.o_list_button_add'); await page.waitForSelector('div[name=partner_id] input'); await page.waitForTimeout(1000);
  const cust = 'div[name=partner_id] input';
  for (const [t, on] of [['محصول', true], ['تعداد', true], ['دارایی', false]]) {
    await page.locator('div[name=invoice_line_ids] .o_optional_columns_dropdown_toggle').first().click(); await page.waitForTimeout(500);
    const inp = page.locator('.o-dropdown--menu .dropdown-item', { hasText: t }).first().locator('input');
    if (on) await inp.check({ force: true }); else await inp.uncheck({ force: true });
    await page.waitForTimeout(500); await page.keyboard.press('Escape');
  }
  await page.waitForTimeout(500);
  await shot('f0', { cust, addline: 'div[name=invoice_line_ids] .o_field_x2many_list_row_add a', post: 'button[name=action_post]', form: '.o_form_sheet' });
  await page.click(cust);
  const word = 'نگین';
  for (let i = 0; i < word.length; i++) {
    await page.keyboard.type(word[i]);
    await shot('fc' + (i + 1), { cust }, { wait: 120 });
  }
  await page.waitForSelector('.o-autocomplete--dropdown-item'); await page.waitForTimeout(500);
  await shot('fcdd', { cust, opt: '.o-autocomplete--dropdown-item' });
  await page.locator('.o-autocomplete--dropdown-item').first().click(); await page.waitForTimeout(900);
  await shot('fcsel', { cust, addline: 'div[name=invoice_line_ids] .o_field_x2many_list_row_add a', header: '.o_inner_group' });

  async function addLine(prefix, text, qty) {
    await page.locator('div[name=invoice_line_ids] .o_field_x2many_list_row_add a').first().click();
    await page.waitForSelector('.o_selected_row div[name=product_id] input'); await page.waitForTimeout(500);
    const prod = '.o_selected_row div[name=product_id] input';
    await shot(prefix + '0', { prod, row: '.o_selected_row' });
    for (let i = 0; i < text.length; i++) { await page.keyboard.type(text[i]); await shot(prefix + 't' + (i + 1), { prod }, { wait: 120 }); }
    await page.waitForSelector('.o-autocomplete--dropdown-item'); await page.waitForTimeout(500);
    await shot(prefix + 'dd', { prod, opt: '.o-autocomplete--dropdown-item' });
    await page.locator('.o-autocomplete--dropdown-item').first().click(); await page.waitForTimeout(1000);
    const q = '.o_selected_row div[name=quantity] input';
    await shot(prefix + 'sel', { row: '.o_selected_row', qty: q, price: '.o_selected_row div[name=price_unit]', tax: '.o_selected_row div[name=tax_ids]' });
    await page.click(q); await page.keyboard.press('Control+A'); await page.keyboard.type(String(qty));
    await shot(prefix + 'qty', { row: '.o_selected_row', qty: q });
  }
  await addLine('la', 'لپ', 2);
  await addLine('lb', 'مانی', 3);
  await page.click('.o_form_sheet .oe_title'); await page.waitForTimeout(1200);
  await shot('flines', { lines: 'div[name=invoice_line_ids] table', totals: '.o_tax_totals, div[name=tax_totals]', post: 'button[name=action_post]' });
  await page.click('button[name=action_post]'); await page.waitForTimeout(2500);
  await shot('fposted', { title: '.oe_title h1', status: '.o_statusbar_status', totals: '.o_tax_totals, div[name=tax_totals]', moadian: 'button:has-text("مودیان"), button:has-text("مؤدیان")', voucher: 'div[name=veron_voucher]', lines: 'div[name=invoice_line_ids] table', banner: '.alert' });
  const invId = (page.url().match(/(\d+)(?!.*\d)/) || [])[1];
  console.log('invoice', invId, page.url());

  await page.goto(B + '/report/html/veron_account_iran.report_official_invoice/' + invId); await page.waitForTimeout(2000);
  await page.addStyleTag({ content: 'html{zoom:1.42} body{padding:24px 0 30px; background:#fff}' }); await page.waitForTimeout(600);
  await shot('official', { head: 'table >> nth=0', seller: 'table.vr-grid >> nth=0', buyer: 'table.vr-grid >> nth=1', lines: 'table.vr-grid >> nth=2', words: 'table.vr-grid >> nth=3' }, { full: true });

  await page.goto(B + '/odoo/action-veron_cheque.action_received'); await page.waitForSelector('.o_data_row, .o_kanban_record'); await page.waitForTimeout(1200);
  await shot('cheques', { rows: '.o_list_table tbody, .o_kanban_renderer', first: '.o_data_row, .o_kanban_record', due: 'th[data-name=due_date]' });
  await page.locator('.o_data_row, .o_kanban_record').first().click(); await page.waitForTimeout(1500);
  await shot('cheque', { sayad: 'div[name=sayad_id]', amount: 'div[name=amount]', words: 'div[name=amount_words]', due: 'div[name=due_date]', status: '.o_statusbar_status', buttons: '.o_statusbar_buttons', sheet: '.o_form_sheet' });

  await page.goto(B + '/report/html/veron_account_iran.report_books/1'); await page.waitForTimeout(2000);
  await page.addStyleTag({ content: 'html{zoom:1.42} body{padding:24px 0 30px; background:#fff}' }); await page.waitForTimeout(600);
  await shot('trial', { head: 'table >> nth=0', table: 'table.vr-grid >> nth=0', total: 'table.vr-grid tr:last-child' }, { full: true });

  fs.writeFileSync(D + '/shots.json', JSON.stringify(shots, null, 1));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
