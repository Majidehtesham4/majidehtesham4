// Section 5: the machine Aria Pack makes, with its prices and barcode; a part it buys, with its supplier
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('stock.menu_stock_root', { sub: 'کالاها را در برنامه‌ی «انبار» تعریف می‌کنیم؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.' });
  await R.menu('محصولات', 'محصولات', { sub: 'از منوی «محصولات» فهرست کالاها را باز می‌کنیم؛ فروش و خرید هم همین فهرست را می‌بینند.' });
  await R.create({ sub: 'محصول اصلی آریا پک: دستگاه بسته‌بندی عمودی.' });
  const top = [200, 100, 1240, 470];
  await R.set('name', 'دستگاه بسته‌بندی عمودی VFFS-320', { focus: top, zoom: 1.2 });
  await R.view({ sub: 'هم فروختنی است و هم موجودی‌اش در انبار ردیابی می‌شود.', focus: top, zoom: 1.2, hold: 1.6, done: 1 });
  if (!(await page.locator('div[name=is_storable] input').isChecked().catch(() => true))) {
    await R.click('div[name=is_storable] input', { wait: 500, afterHold: 0.5, focus: top, zoom: 1.2, after: true });
  }
  if (await page.locator('div[name=purchase_ok] input').isChecked().catch(() => false)) {
    await R.click('div[name=purchase_ok] input', { sub: 'این دستگاه را می‌سازیم، نمی‌خریم؛ پس «قابل خرید» را برمی‌داریم.', wait: 500, afterHold: 0.8, focus: top, zoom: 1.2 });
  }
  await R.set('list_price', '4850000000', { sub: 'قیمت فروش به ریال…', step: 1 });
  await R.set('standard_price', '3100000000', { sub: '…و بهای تمام‌شده.' });
  await R.many2one('categ_id', 'ماشین', { sub: 'دسته‌ی کالا: ماشین‌آلات بسته‌بندی.' });
  await R.set('default_code', 'VFFS-320', { sub: 'کد کالا…' });
  await R.set('barcode', '6260001000011', { sub: '…و بارکد؛ در انبار و فروش با اسکنر خوانده می‌شود.' });
  await R.saveForm({ sub: 'ذخیره می‌کنیم.', done: 2, afterHold: 1.2 });
  // a part that is bought
  await R.click(page.locator('.o_breadcrumb a, .breadcrumb-item a').first(), { sub: 'حالا یکی از قطعاتی که برای ساخت دستگاه می‌خریم.', step: 2, wait: 1500, newpage: true, afterHold: 0.6 });
  await R.create({});
  await R.set('name', 'موتور گیربکس ۱٫۵ کیلووات', { focus: top, zoom: 1.2 });
  if (await page.locator('div[name=sale_ok] input').isChecked().catch(() => false)) {
    await R.click('div[name=sale_ok] input', { sub: 'قطعه را نمی‌فروشیم؛ فقط می‌خریم.', wait: 500, afterHold: 0.6, focus: top, zoom: 1.2 });
  }
  await R.set('standard_price', '96000000', { sub: 'بهای خرید تقریبی…' });
  await R.many2one('categ_id', 'قطعات', { sub: '…و دسته‌ی «قطعات و مواد اولیه».' });
  await R.set('default_code', 'PRT-MTR15', {});
  // its supplier
  await R.click(page.locator('.o_notebook .nav-link', { hasText: 'خرید' }).first(), { sub: 'در زبانه‌ی «خرید» تأمین‌کننده‌ی آن را می‌نویسیم.', step: 3, wait: 800, afterHold: 0.6 });
  await R.click(page.locator('div[name=seller_ids] .o_field_x2many_list_row_add a').first(), { wait: 800, afterHold: 0.4,
    focus: 'div[name=seller_ids]', zoom: 1.3 });
  await R.type('.o_selected_row div[name=partner_id] input', 'پیشرو', { focus: 'div[name=seller_ids]', zoom: 1.3, pick: 'پیشرو', pickSub: 'شرکت قطعات صنعتی پیشرو.' });
  const price = page.locator('.o_selected_row div[name=price] input').first();
  if (await price.count()) await R.type(price, '96000000', { sub: 'و قیمت خرید از او؛ در سفارش خرید خودکار می‌آید.', focus: 'div[name=seller_ids]', zoom: 1.3 });
  await R.saveForm({ sub: 'ذخیره.', done: 4, afterHold: 1.2 });
  await R.click(page.locator('.o_breadcrumb a, .breadcrumb-item a').first(), { sub: 'همه‌ی ماشین‌آلات، قطعات و مواد اولیه‌ی آریا پک در یک فهرست.', step: 4, wait: 1500, newpage: true, afterHold: 0.6 });
  await R.click('.o_switch_view.o_list', { wait: 1500, newpage: true, afterHold: 2.2, done: 5 });
  await R.view({ sub: 'کالاها آماده است. بخش بعد: انبارها و موجودی اول دوره.', cam: 'full', hold: 2.4 });
};
