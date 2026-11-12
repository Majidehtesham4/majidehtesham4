// Section 9: an opportunity in the CRM, its quotation, the sales order, the machines delivered and the invoice
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('crm.crm_menu_root', { sub: 'فروش از «مدیریت ارتباط با مشتری» شروع می‌شود؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.',
    afterSub: 'هر فرصت فروش یک کارت است و از راست به چپ، مرحله به مرحله جلو می‌رود.', hold: 1.8 });
  await R.tourMenus([
    ['فروش ها', 'منوی «فروش‌ها»: فرصت‌ها، فعالیت‌ها، پیش‌فاکتورها و مشتریان.'],
    ['گزارش', '«گزارش»: پیش‌بینی فروش و تحلیل فرصت‌ها.'],
    ['پیکربندی', 'و «پیکربندی»: تیم‌های فروش، مرحله‌ها و برچسب‌ها.'],
  ], { step: 0 });
  // the opportunity
  await R.click('.o-kanban-button-new', { sub: 'شرکت آفتاب طلایی دو دستگاه بسته‌بندی می‌خواهد؛ یک فرصت فروش تازه.', wait: 1200, afterHold: 0.6,
    afterCam: { focus: '.o_kanban_quick_create', zoom: 1.35 } });
  const qc = { focus: '.o_kanban_quick_create', zoom: 1.35 };
  await R.type('.o_kanban_quick_create div[name=commercial_partner_id] input', 'آفتاب طلایی', { sub: 'مشتری…', ...qc, pick: 'آفتاب طلایی' });
  await R.type('.o_kanban_quick_create div[name=name] input', 'دو دستگاه VFFS-320 برای خط چای', { sub: '…عنوان فرصت…', ...qc });
  await R.type('.o_kanban_quick_create div[name=expected_revenue] input', '9700000000', { sub: '…و درآمد مورد انتظار.', ...qc });
  await R.click('.o_kanban_quick_create .o_kanban_add', { sub: '«افزودن»؛ کارت در ستون «جدید» می‌نشیند.', wait: 1500, afterHold: 1.4, afterCam: 'full' });
  await R.click(page.locator('.o_kanban_record', { hasText: 'VFFS-320' }).first(), { sub: 'کارت را باز می‌کنیم.', wait: 1800, newpage: true, afterHold: 1.0 });
  await R.click(page.locator('.o_statusbar_status button', { hasText: 'پیشنهاد' }).first(), { sub: 'مذاکره جلو رفت؛ مرحله را «پیشنهاد» می‌کنیم.', wait: 1200, afterHold: 1.4, done: 1 });
  // the quotation
  await R.click('button[name=action_sale_quotations_new]:visible', { sub: 'از همین فرصت، «پیش‌فاکتور جدید» می‌سازیم؛ مشتری خودش پر می‌شود.', step: 1, wait: 2200, newpage: true, afterHold: 1.2 });
  const lines = ['div[name=order_line]'];
  await R.click(page.locator('div[name=order_line] .o_field_x2many_list_row_add a').first(), { sub: 'دستگاه را اضافه می‌کنیم…', wait: 900, afterHold: 0.3, focus: lines, zoom: 1.3 });
  await R.type('.o_selected_row div[name=product_id] input, .o_selected_row div[name=product_template_id] input', 'VFFS-320', { focus: lines, zoom: 1.3, pick: 'VFFS-320' });
  await R.type('.o_selected_row div[name=product_uom_qty] input', '2', { sub: '…دو دستگاه؛ قیمت از کارت کالا می‌آید.', focus: lines, zoom: 1.3 });
  await page.keyboard.press('Escape');
  await R.view({ sub: 'جمع، مالیات بر ارزش افزوده و مبلغ کل حساب شد.', focus: ['div[name=order_line]', 'div[name=tax_totals]'], zoom: 1.25, hold: 1.8 });
  await R.saveForm({ sub: 'ذخیره؛ پیش‌فاکتور را می‌شود چاپ کرد یا با ایمیل فرستاد.', done: 2 });
  // the order
  await R.click('.o_statusbar_buttons button[name=action_confirm]:visible', { sub: 'مشتری پذیرفت: «تأیید»؛ پیش‌فاکتور سفارش فروش می‌شود.', step: 2, wait: 2200, afterHold: 1.6, done: 3 });
  // the delivery
  await R.click('button[name=action_view_delivery]', { sub: 'دستگاه‌ها را از دکمه‌ی «تحویل» از انبار می‌فرستیم.', step: 3, wait: 2000, newpage: true, afterHold: 1.2 });
  await R.click('.o_statusbar_buttons button[name=button_validate]:visible', { sub: '«اعتبارسنجی»؛ دستگاه‌ها از انبار خارج می‌شوند.', wait: 2200, afterHold: 1.6, done: 4 });
  const conf = page.locator('.modal .modal-footer button.btn-primary:visible').first();
  if (await conf.count()) await R.click(conf, { wait: 2000, afterHold: 1.0 });
  await R.click(page.locator('.o_breadcrumb a, .breadcrumb-item a', { hasText: 'S0' }).first(), { sub: 'به سفارش فروش برمی‌گردیم.', wait: 1600, newpage: true, afterHold: 0.8 });
  // the invoice
  await R.click(page.locator('.o_statusbar_buttons button:visible', { hasText: 'ایجاد فاکتور' }).first(), { sub: 'و فاکتور فروش: «ایجاد فاکتور».', step: 4, wait: 1500, afterHold: 1.0,
    afterCam: { focus: '.modal-content', zoom: 1.25 } });
  await R.click('.modal button[name=create_invoices]', { sub: 'فاکتور از روی سفارش ساخته می‌شود.', wait: 2500, newpage: true, afterHold: 1.4 });
  await R.view({ sub: 'سطرها، مالیات و مشتری همه آماده است.', focus: ['div[name=invoice_line_ids]', 'div[name=tax_totals]'], zoom: 1.2, hold: 1.8 });
  await R.click('.o_statusbar_buttons button[name=action_post]:visible', { sub: '«تأیید»؛ فاکتور رسمی شد و سند حسابداری فروش خودکار ثبت می‌شود.', wait: 2500, afterHold: 2.0, done: 5 });
  await R.view({ sub: 'فروش تمام شد. بخش بعد: ارسال همین فاکتور به سامانه‌ی مؤدیان.', cam: 'full', hold: 2.4 });
};
