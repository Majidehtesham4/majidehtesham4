// Section 4: a customer and a supplier with their ids, then a list of companies imported from Excel
const path = require('path');
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('contacts.menu_contacts', { sub: 'همه‌ی مشتریان و تأمین‌کنندگان در برنامه‌ی «مخاطبان» هستند؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.' });
  await R.create({ sub: 'اولین مشتری: یک شرکت صنایع غذایی که ماشین بسته‌بندی می‌خرد.' });
  const form = [200, 100, 1240, 420];
  await R.select('company_type', 'شرکت', { sub: 'نوع مخاطب را «شرکت» انتخاب می‌کنیم.', focus: form, zoom: 1.25 });
  await R.set('name', 'شرکت صنایع غذایی آفتاب طلایی', { focus: form, zoom: 1.25 });
  await R.set('street', 'شهرک صنعتی بزرگ شیراز، خیابان ۷', { sub: 'نشانی و تلفن…' });
  await R.set('city', 'شیراز', {});
  await R.set('phone', '071-37741230', {});
  await R.set('vat', '411876543210', { sub: 'کد اقتصادی مشتری؛ برای فاکتور رسمی و سامانه‌ی مؤدیان لازم است.', step: 1, done: 1 });
  await R.set('veron_national_id', '10320540002', { sub: 'و شناسه‌ی ملی شرکت؛ برنامه درستی رقم کنترل آن را می‌سنجد.' });
  await R.saveForm({ sub: 'ذخیره می‌کنیم.', done: 2, afterHold: 1.4 });
  await R.click(page.locator('.o_breadcrumb a, .breadcrumb-item a').first(), { sub: 'حالا یک تأمین‌کننده: فروشنده‌ی ورق فولادی.', step: 2, wait: 1500, newpage: true, afterHold: 0.6 });
  await R.create({});
  await R.select('company_type', 'شرکت', { focus: form, zoom: 1.25 });
  await R.set('name', 'شرکت فولاد پویا', { focus: form, zoom: 1.25 });
  await R.set('city', 'اصفهان', {});
  await R.set('vat', '411345678901', {});
  await R.set('veron_national_id', '10862340004', {});
  await R.saveForm({ sub: 'مشتری و تأمین‌کننده هر دو «مخاطب» هستند؛ فرقشان در سندهایی است که برایشان می‌زنیم.', done: 3, afterHold: 1.6 });
  // a whole list at once, from an Excel file
  await R.click(page.locator('.o_breadcrumb a, .breadcrumb-item a').first(), { sub: 'بقیه‌ی شرکت‌ها را یک‌جا از فایل اکسل وارد می‌کنیم.', step: 3, wait: 1500, newpage: true, afterHold: 0.6 });
  await R.click('.o_switch_view.o_list', { sub: 'اول نمای فهرستی را انتخاب می‌کنیم.', wait: 1500, newpage: true, afterHold: 0.8 });
  await R.click(page.locator('.o_cp_action_menus button, .o_control_panel_breadcrumbs .fa-cog').first(), { wait: 700, afterHold: 0.6,
    afterCam: { focus: [700, 40, 740, 260], zoom: 1.35 } });
  await R.click(R.menuItem('ورود رکورد'), { sub: '«ورود رکورد» را می‌زنیم و فایل اکسل را انتخاب می‌کنیم.', wait: 1500, newpage: true, afterHold: 0.6 });
  await page.locator('input[type=file]').first().setInputFiles(path.join(__dirname, '..', 'assets', 'contacts.xlsx'));
  await R.view({ sub: 'برنامه ستون‌های فایل را خودش با فیلدها جور می‌کند: نام، تلفن، شهر.', wait: 2500, hold: 2.2 });
  await R.click(page.locator('button:visible', { hasText: /^ورود$|^درون‌ریزی$|^وارد کردن$/ }).first(), { sub: 'و با یک کلیک همه وارد می‌شوند.', wait: 3000, newpage: true, afterHold: 1.6, done: 4 });
  await R.view({ sub: 'فهرست مخاطبان آماده است؛ با جست‌وجو و فیلتر هر کدام را زود پیدا می‌کنیم.', step: 4, hold: 2.2, cam: 'full' });
  await R.search('فولاد', { sub: 'مثلاً با نوشتن «فولاد» تأمین‌کننده‌ی فولاد پیدا می‌شود.', done: 5 });
  await R.view({ sub: 'مخاطبان ثبت شد. بخش بعد: کالاها و ماشین‌آلاتی که آریا پک می‌سازد.', cam: 'full', hold: 2.4 });
};
