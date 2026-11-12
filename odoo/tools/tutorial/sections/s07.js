// Section 7: a request for quotation to a supplier, the purchase order, the goods received, the vendor bill and its payment
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('purchase.menu_purchase_root', { sub: 'از صفحه‌ی برنامه‌ها «خرید» را باز می‌کنیم.', afterSub: 'همه‌ی درخواست‌های پیش‌فاکتور و سفارش‌های خرید اینجاست.', hold: 1.6 });
  await R.create({ sub: 'برای ساخت دستگاه‌ها ورق استیل و سنسور لازم داریم؛ یک درخواست پیش‌فاکتور تازه.' });
  const head = [500, 120, 940, 300];
  await R.many2one('partner_id', 'فولاد پویا', { sub: 'تأمین‌کننده: شرکت فولاد پویا.', focus: head, zoom: 1.3, pick: 'فولاد پویا' });
  const lines = ['div[name=order_line]'];
  const line = async (name, qty, price, sub) => {
    await R.click(page.locator('div[name=order_line] .o_field_x2many_list_row_add a').first(), { sub, wait: 900, afterHold: 0.3, focus: lines, zoom: 1.3 });
    await R.type('.o_selected_row div[name=product_id] input', name, { focus: lines, zoom: 1.3, pick: name });
    await R.type('.o_selected_row div[name=product_qty] input', String(qty), { focus: lines, zoom: 1.3 });
    await R.type('.o_selected_row div[name=price_unit] input', String(price), { focus: lines, zoom: 1.3 });
  };
  await line('ورق استیل', 500, 1450000, 'کالای اول: ۵۰۰ کیلوگرم ورق استیل، کیلویی ۱٬۴۵۰٬۰۰۰ ریال.');
  await line('سنسور نوری', 20, 18500000, 'کالای دوم: ۲۰ عدد سنسور نوری.');
  await page.keyboard.press('Escape');
  await R.view({ sub: 'جمع، مالیات بر ارزش افزوده و مبلغ کل خودکار حساب می‌شود.', focus: ['div[name=order_line]', 'div[name=tax_totals]'], zoom: 1.3, hold: 1.8 });
  await R.saveForm({ sub: 'ذخیره می‌کنیم؛ می‌شود آن را با ایمیل برای تأمین‌کننده فرستاد.', done: 1 });
  await R.click('.o_statusbar_buttons button[name=button_confirm]:visible', { sub: 'قیمت را پذیرفتیم: «تأیید سفارش»؛ درخواست به سفارش خرید تبدیل می‌شود.', step: 1, wait: 1800, afterHold: 1.6, done: 2 });
  // the goods arrive
  await R.click('button[name=action_view_picking]', { sub: 'کالا که رسید، از دکمه‌ی «رسید» آن را در انبار تحویل می‌گیریم.', step: 2, wait: 1800, newpage: true, afterHold: 1.2 });
  await R.view({ sub: 'مقدارها را با بار رسیده مقایسه می‌کنیم.', focus: 'div[name=move_ids]', zoom: 1.25, hold: 1.6 });
  await R.click('.o_statusbar_buttons button[name=button_validate]:visible', { sub: 'و «اعتبارسنجی»؛ کالا وارد انبار مرکزی می‌شود و موجودی بالا می‌رود.', wait: 2000, afterHold: 1.8, done: 3 });
  const conf = page.locator('.modal button.btn-primary:visible').first();
  if (await conf.count()) await R.click(conf, { wait: 1800, afterHold: 1.0 });
  // the bill: made from the list of purchase orders (the order is ticked, then «Create Bills»)
  await R.menu('سفارشات', 'سفارشات خرید', { sub: 'فاکتور تأمین‌کننده رسید؛ از فهرست سفارش‌های خرید صورتحساب را می‌سازیم.', step: 3 });
  await R.click(page.locator('.o_data_row .o_list_record_selector input').first(), { sub: 'سفارش را علامت می‌زنیم…', wait: 700, afterHold: 0.6 });
  await R.click('button[name=action_create_invoice]:visible', { sub: '…و «ایجاد صورتحساب»؛ سطرهای فاکتور از روی سفارش ساخته می‌شود.', wait: 2200, newpage: true, afterHold: 1.4 });
  const date = page.locator('div[name=invoice_date] input').first();
  await R.click(date, { sub: 'تاریخ فاکتور را می‌زنیم؛ تقویم شمسی است.', wait: 700, afterHold: 0.8, focus: [500, 100, 940, 380], zoom: 1.3,
    afterCam: { focus: [500, 100, 940, 500], zoom: 1.25 } });
  await R.click(page.locator('.o_datetime_picker .o_today, .o_date_item_cell.o_today, .o_datetime_picker button.o_today').first(), { wait: 700, afterHold: 0.8 });
  await R.type('div[name=ref] input', 'FP-1405-0815', { sub: 'و شماره‌ی فاکتور خود تأمین‌کننده را.', focus: [500, 100, 940, 380], zoom: 1.3 });
  await R.view({ sub: 'سطرهای فاکتور همان سطرهای سفارش است؛ چیزی دوباره نوشته نمی‌شود.', focus: ['div[name=invoice_line_ids]', 'div[name=tax_totals]'], zoom: 1.2, hold: 1.8 });
  await R.click('.o_statusbar_buttons button[name=action_post]:visible', { sub: '«تأیید»؛ سند حسابداری خرید خودکار ثبت می‌شود.', wait: 2000, afterHold: 1.6, done: 4 });
  // the payment
  await R.click('.o_statusbar_buttons button[name=action_register_payment]:visible', { sub: 'حالا پرداخت: «ثبت پرداخت».', step: 4, wait: 1800, afterHold: 1.0,
    afterCam: { focus: '.modal-content', zoom: 1.25 } });
  const journal = page.locator('.modal div[name=journal_id]').first();
  if (await journal.count()) {
    const opt = journal.locator('.o_radio_item, .form-check', { hasText: 'ملت' }).first();
    if (await opt.count()) await R.click(opt.locator('input, label').first(), { sub: 'از حساب بانک ملت.', wait: 600, afterHold: 0.8, focus: '.modal-content', zoom: 1.25 });
    else {
      const inp = journal.locator('input').first();
      if (await inp.count()) await R.type(inp, 'ملت', { sub: 'از حساب بانک ملت.', pick: 'ملت', focus: '.modal-content', zoom: 1.25 });
    }
  }
  await R.click('.modal button[name=action_create_payments]', { sub: 'و «ایجاد پرداخت».', wait: 2200, afterHold: 2.0, afterCam: 'full', done: 5 });
  await R.view({ sub: 'فاکتور پرداخت شد. خرید، انبار و حسابداری بدون هیچ دوباره‌کاری به هم وصل‌اند.', hold: 2.2 });
  await R.view({ sub: 'خرید تمام شد. بخش بعد: تولید دستگاه در کارگاه.', cam: 'full', hold: 2.4 });
};
