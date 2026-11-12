// Section 8: the bill of materials of the machine, a manufacturing order, its components reserved, the production
// recorded and the machines made in stock
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('mrp.menu_mrp_root', { sub: 'ساخت دستگاه‌ها در برنامه‌ی «تولید» است؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.',
    afterSub: 'همه‌ی سفارش‌های تولید کارخانه اینجاست.', hold: 1.6 });
  await R.tourMenus([
    ['عملیات', 'منوی «عملیات»: سفارش‌های تولید، کارهای مانده و اسقاط.'],
    ['محصولات', 'منوی «محصولات»: کالاها و صورت مواد اولیه‌ی هر دستگاه.'],
    ['پیکربندی', 'و «پیکربندی»: تنظیمات تولید.'],
  ], { step: 0 });
  // the bill of materials
  await R.menu('محصولات', 'صورت های مواد اولیه', { sub: 'اول فرمول ساخت دستگاه را تعریف می‌کنیم: «صورت مواد اولیه».' });
  await R.create({ sub: 'یک صورت مواد اولیه‌ی تازه.' });
  await R.many2one('product_tmpl_id', 'VFFS-320', { sub: 'محصول: دستگاه بسته‌بندی عمودی VFFS-320.', pick: 'VFFS-320' });
  const lines = ['div[name=bom_line_ids]'];
  const comp = async (name, qty, sub) => {
    await R.click(page.locator('div[name=bom_line_ids] .o_field_x2many_list_row_add a').first(), { sub, wait: 900, afterHold: 0.3, focus: lines, zoom: 1.3 });
    await R.type('.o_selected_row div[name=product_id] input', name, { focus: lines, zoom: 1.3, pick: name });
    await R.type('.o_selected_row div[name=product_qty] input', String(qty), { focus: lines, zoom: 1.3 });
  };
  await comp('ورق استیل', 250, 'برای ساخت یک دستگاه: ۲۵۰ کیلوگرم ورق استیل…');
  await comp('موتور گیربکس', 1, '…یک موتور گیربکس…');
  await comp('تابلو برق', 1, '…یک تابلو برق و PLC…');
  await comp('سنسور نوری', 4, '…و چهار سنسور نوری.');
  await page.keyboard.press('Escape');
  await R.saveForm({ sub: 'ذخیره می‌کنیم؛ از این به بعد هر سفارش تولید قطعاتش را از همین فرمول برمی‌دارد.', done: 1 });
  // the manufacturing order
  await R.menu('عملیات', 'سفارشات تولید', { sub: 'حالا سفارش تولید: دو دستگاه برای سفارش مشتری.', step: 1 });
  await R.create({});
  await R.many2one('product_id', 'VFFS-320', { sub: 'محصولی که می‌سازیم…', pick: 'VFFS-320' });
  await R.set('product_qty', '2', { sub: '…و تعداد: دو دستگاه.' });
  await R.view({ sub: 'قطعات لازم خودکار از صورت مواد اولیه و به اندازه‌ی دو دستگاه آمد.', focus: 'div[name=move_raw_ids]', zoom: 1.25, hold: 2.0, done: 2 });
  await R.click('.o_statusbar_buttons button[name=action_confirm]:visible', { sub: '«تأیید کردن»؛ قطعات در انبار برای این سفارش رزرو می‌شود.', step: 2, wait: 2200, afterHold: 1.4 });
  await R.view({ sub: 'ستون موجودی نشان می‌دهد همه‌ی قطعات در انبار هست.', focus: 'div[name=move_raw_ids]', zoom: 1.25, hold: 2.0, done: 3 });
  // the production
  await R.click(page.locator('.o_statusbar_buttons button[name=button_mark_done]:visible').first(), { sub: 'ساخت که تمام شد: «تولید»؛ قطعات از انبار کم و دستگاه‌ها اضافه می‌شوند.', step: 3, wait: 2500, afterHold: 1.4 });
  for (let k = 0; k < 2; k++) {
    const conf = page.locator('.modal .modal-footer button.btn-primary:visible').first();
    if (await conf.count()) await R.click(conf, { sub: 'تأیید می‌کنیم.', wait: 2500, afterHold: 1.2 });
  }
  await R.view({ sub: 'سفارش تولید «انجام شده» شد.', hold: 2.0, done: 4 });
  // the machines in stock
  await R.menu('محصولات', 'محصولات', { sub: 'دستگاه‌های ساخته‌شده حالا در انبار موجودند.', step: 4 });
  await R.search('VFFS', { sub: 'دستگاه VFFS-320 را جست‌وجو می‌کنیم.', cam: 'full', afterHold: 1.6 });
  await R.click(page.locator('.o_kanban_record:not(.o_kanban_ghost), .o_data_row').first(), { sub: 'موجودی آن دو دستگاه است؛ آماده‌ی فروش.', wait: 1800, newpage: true, afterHold: 2.2, done: 5 });
  await R.view({ sub: 'تولید تمام شد. بخش بعد: فروش و مدیریت ارتباط با مشتری.', cam: 'full', hold: 2.4 });
};
