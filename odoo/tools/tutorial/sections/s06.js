// Section 6: the main warehouse, the opening stock by a count, the kardex of a product, the stock report
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.goto('/odoo/inventory', { sub: 'برنامه‌ی «انبار»: رسیدها، تحویل‌ها و تولیدات در یک نگاه.', step: 0, hold: 1.8 });
  await R.menu('پیکربندی', 'انبارها', { sub: 'اول انبار اصلی شرکت را نام‌گذاری می‌کنیم.' });
  await R.click(page.locator('.o_data_row').first(), { wait: 1500, newpage: true, afterHold: 0.6 });
  await R.set('name', 'انبار مرکزی آریا پک', { focus: [300, 100, 1140, 300], zoom: 1.3 });
  await R.saveForm({ sub: 'ذخیره؛ همه‌ی رسیدها و تحویل‌ها از این انبار است.', done: 1 });
  await R.menu('عملیات', 'فهرست فیزیکی', { sub: 'موجودی اول دوره را با «شمارش» وارد می‌کنیم.', step: 1 });
  await R.view({ sub: 'بخشی از کالاها قبلاً شمرده شده‌اند؛ دو قلم دیگر را اضافه می‌کنیم.', hold: 1.6, focus: [0, 80, 1440, 420], zoom: 1.2 });
  const listArea = [0, 80, 1440, 460];
  const add = async (name, qty, sub) => {
    await R.click(page.locator('.o_list_button_add, button.o_list_button_add').first(), { sub, wait: 900, afterHold: 0.3, focus: listArea, zoom: 1.2 });
    await R.type('.o_selected_row div[name=product_id] input', name, { focus: listArea, zoom: 1.2, pick: name });
    await R.type('.o_selected_row div[name=inventory_quantity] input', String(qty), { focus: listArea, zoom: 1.2 });
    await page.keyboard.press('Enter');
    await R.settle(800);
  };
  await add('ورق استیل', 1200, 'ورق استیل ضدزنگ: ۱۲۰۰ کیلوگرم.');
  await page.keyboard.press('Escape');
  await add('موتور گیربکس', 8, 'موتور گیربکس: ۸ عدد.');
  await page.keyboard.press('Escape');
  await R.view({ sub: 'ستون «تفاوت» نشان می‌دهد چه مقدار به موجودی اضافه می‌شود.', hold: 1.8, focus: listArea, zoom: 1.2, done: 2 });
  await R.click(page.locator('button:visible', { hasText: 'اعمال بر همه' }).first(), { sub: 'با «اعمال بر همه» شمارش ثبت می‌شود.', step: 2, wait: 1200, afterHold: 0.8 });
  const confirm = page.locator('.modal button.btn-primary:visible').first();
  if (await confirm.count()) await R.click(confirm, { sub: 'تأیید می‌کنیم.', wait: 1500, afterHold: 1.0 });
  await R.view({ sub: 'موجودی اول دوره ثبت شد و سند انبار آن خودکار ساخته می‌شود.', hold: 1.8, done: 3 });
  // the kardex
  await R.menu('گزارش', 'کاردکس', { sub: 'کاردکس هر کالا: ورود، خروج و مانده، ردیف به ردیف.', step: 3 });
  const prod = page.locator('div[name=product_id] input, div[name=product_ids] input').first();
  if (await prod.count()) {
    await R.type(prod, 'ورق استیل', { pick: 'ورق استیل', focus: '.modal-content, .o_form_sheet', zoom: 1.2 });
    const show = page.locator('.modal-footer button.btn-primary, .o_form_view button.btn-primary').first();
    if (await show.count()) await R.click(show, { sub: 'کاردکس ورق استیل را می‌بینیم.', wait: 2500, newpage: true, afterHold: 2.4, done: 4 });
  } else {
    await R.view({ hold: 2.4, done: 4 });
  }
  await R.menu('گزارش', 'موجودی کالا', { sub: 'و گزارش موجودی: هر کالا چه مقدار در انبار است.', step: 4 });
  await R.view({ hold: 2.2, done: 5, focus: [0, 80, 1440, 520], zoom: 1.15 });
  await R.view({ sub: 'انبار آماده است. بخش بعد: خرید قطعات از تأمین‌کنندگان.', cam: 'full', hold: 2.4 });
};
