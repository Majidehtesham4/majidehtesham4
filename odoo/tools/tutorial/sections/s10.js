// Section 10: the tax memory of the company, the sales invoice prepared for Moadian, its tax number and check;
// sending is shown, not done (it goes to the tax organization)
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('account.menu_finance', { sub: 'سامانه‌ی مؤدیان در برنامه‌ی «حسابداری» است؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.', hold: 1.4 });
  await R.tourMenus([
    ['مشتریان', 'منوی «مشتریان»: فاکتورهای فروش، برگشت از فروش و دریافت‌ها.'],
    ['حسابداری ایرانی', '«حسابداری ایرانی»: دفترها و گزارش‌های رسمی.'],
    ['پیکربندی', 'و «پیکربندی»: تنظیمات حسابداری، از جمله سامانه‌ی مؤدیان.'],
  ], { step: 0 });
  // the settings
  await R.menu('پیکربندی', 'تنظیمات', { sub: 'اول تنظیمات مؤدیان را باز می‌کنیم.' });
  await R.type('.o_control_panel .o_searchview_input, .o_searchview input', 'مودیان', { sub: 'در جست‌وجوی تنظیمات «مودیان» را می‌نویسیم.', cam: 'full', after: true });
  const box = 'div[name=veron_moadian_memory_id]';
  await R.type(`${box} input`, 'A1B2C3', { sub: 'شناسه‌ی یکتای حافظه‌ی مالیاتی شرکت را از کارپوشه‌ی سامانه‌ی مؤدیان وارد می‌کنیم.', focus: [200, 100, 1240, 480], zoom: 1.2 });
  const key = page.locator('button[name=action_veron_moadian_new_key]').first();
  if (await key.count()) await R.hover(key, { sub: 'کلید امضا همین‌جا در خود ERP ساخته می‌شود و هیچ‌وقت نمایش داده نمی‌شود؛ فقط درخواست گواهی برای سازمان مالیاتی دانلود می‌شود.', mark: true, hold: 1.4, focus: [200, 100, 1240, 480], zoom: 1.2 });
  const active = page.locator('div[name=veron_moadian_active] input').first();
  if (await active.count() && !(await active.isChecked())) await R.click(active, { sub: 'ارسال به مؤدیان را روشن می‌کنیم؛ باز هم هر فاکتور را مدیر مالی جدا می‌فرستد.', wait: 500, afterHold: 0.8, focus: [200, 100, 1240, 480], zoom: 1.2 });
  await R.saveForm({ sub: 'ذخیره می‌کنیم.', done: 1 });
  // the invoice of section 9
  const invoice = async (sub, step) => {
    await R.menu('مشتریان', 'فاکتورها', { sub, step });
    await R.click(page.locator('.o_data_row', { hasText: 'آفتاب' }).first(), { wait: 1800, newpage: true, afterHold: 0.8 });
  };
  await invoice('حالا فاکتور فروشی که در بخش ۹ صادر شد.', 1);
  await R.view({ sub: 'کد اقتصادی و نشانی خریدار از کارت مشتری می‌آید؛ همان که در بخش ۴ ثبت شد.', focus: [500, 120, 940, 330], zoom: 1.3, hold: 2.0 });
  await R.click('.o_statusbar_buttons button[name=action_veron_moadian_prepare]:visible', { sub: '«آماده‌سازی برای مودیان»: فاکتور با الگوی سازمان مالیاتی ساخته و سنجیده می‌شود.', wait: 2200, afterHold: 1.0 });
  await R.click(page.locator('.o_notebook .nav-link', { hasText: 'مودیان' }).first(), { sub: 'نتیجه در زبانه‌ی «سامانه مودیان» است.', wait: 900, afterHold: 0.6 });
  await R.view({ sub: 'یک ایراد پیدا شد: دستگاه شناسه‌ی ۱۳ رقمی کالا در فهرست سازمان مالیاتی را ندارد. پیش از ارسال باید رفع شود.', focus: '.o_notebook .tab-pane.active .alert', zoom: 1.3, hold: 2.6, done: 2 });
  // the goods id on the product
  await R.menu('مشتریان', 'محصولات', { sub: 'شناسه را روی کارت خود کالا می‌نویسیم؛ برای همه‌ی فاکتورهای بعدی می‌ماند.', step: 2 });
  await R.search('VFFS', { cam: 'full', afterHold: 1.0 });
  await R.click(page.locator('.o_kanban_record:not(.o_kanban_ghost), .o_data_row').first(), { wait: 1800, newpage: true, afterHold: 0.8 });
  await R.set('veron_sstid', '2720000123456', { sub: 'شناسه‌ی کالا/خدمت را از فهرست سازمان مالیاتی وارد می‌کنیم.' });
  await R.saveForm({ sub: 'ذخیره.', done: 3 });
  await invoice('دوباره سراغ فاکتور می‌رویم.', 3);
  await R.click('.o_statusbar_buttons button[name=action_veron_moadian_prepare]:visible', { sub: 'و دوباره «آماده‌سازی برای مودیان».', wait: 2200, afterHold: 1.0 });
  await R.click(page.locator('.o_notebook .nav-link', { hasText: 'مودیان' }).first(), { wait: 900, afterHold: 0.6 });
  await R.view({ sub: 'این بار ایرادی نیست: شماره‌ی مالیاتی ۲۲ رقمی ساخته شد و وضعیت «آماده» است.', focus: 'div[name=veron_tax_id]', zoom: 1.3, hold: 2.4 });
  await R.view({ sub: 'متن فاکتور به الگوی سامانه هم اینجاست؛ پیش از ارسال قابل بازبینی است.', focus: 'div[name=veron_moadian_payload]', zoom: 1.2, hold: 2.0, done: 4 });
  const send = page.locator('.o_statusbar_buttons button[name=action_veron_moadian_send]:visible').first();
  if (await send.count()) await R.hover(send, { sub: '«ارسال به سامانه مودیان» را فقط مدیر مالی و پس از بررسی می‌زند؛ هیچ فاکتوری خودکار فرستاده نمی‌شود.', step: 4, mark: true, hold: 2.0, focus: [300, 40, 1140, 300], zoom: 1.3 });
  await R.view({ sub: 'نتیجه (پذیرفته یا رد با دلیل) هر ساعت از سامانه گرفته می‌شود؛ فاکتور فرستاده‌شده فقط با برگشت از فروش اصلاح می‌شود.', hold: 2.4, done: 5, cam: 'full' });
  await R.view({ sub: 'مؤدیان تمام شد. بخش بعد: حسابداری؛ چک، اسناد و گزارش‌ها.', cam: 'full', hold: 2.4 });
};
