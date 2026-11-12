// Section 2: the company Aria Pack (name, logo, address, tax ids, currency) and two users with their access
const path = require('path');

module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.goto('/odoo/settings', { sub: 'همه‌ی تنظیمات پایه از برنامه‌ی «تنظیمات» شروع می‌شود.', step: 0, hold: 1.4 });
  const top = (t) => page.locator('.o_menu_sections button, .o_menu_sections a', { hasText: t }).first();
  const item = (t) => page.locator('.o-dropdown--menu .dropdown-item, .o-dropdown--menu .o-dropdown-item', { hasText: t }).first();
  await R.click(top('کاربران و شرکت'), { sub: 'از منوی «کاربران و شرکت‌ها» سراغ مشخصات شرکت می‌رویم.', wait: 600, afterHold: 0.8,
    afterCam: { focus: [700, 0, 740, 260], zoom: 1.35 } });
  await R.click(item('شرکت'), { wait: 1500, newpage: true, afterHold: 0.8 });
  await R.click(page.locator('.o_data_row').first(), { sub: 'شرکت پیش‌فرض را باز می‌کنیم تا مشخصات آریا پک را بنویسیم.', wait: 1500, newpage: true, afterHold: 0.8 });
  const sheet = '.o_form_sheet';
  await R.type('div[name=name] input', 'آریا پک', { sub: 'نام شرکت: آریا پک، سازنده‌ی ماشین‌آلات بسته‌بندی.', focus: [500, 120, 940, 360], zoom: 1.35 });
  // the logo
  const logoInput = page.locator('div[name=logo] input[type=file]').first();
  await R.hover('div[name=logo]', { sub: 'لوگوی شرکت را بارگذاری می‌کنیم؛ روی فاکتورها و گزارش‌ها چاپ می‌شود.', step: 1 });
  await logoInput.setInputFiles(path.join(__dirname, '..', 'assets', 'aryapack_logo.png'));
  await R.view({ wait: 1200, hold: 1.6, focus: [900, 100, 540, 330], zoom: 1.35 });
  await R.type('div[name=street] input', 'شهرک صنعتی شمس‌آباد، خیابان صنعت، پلاک ۱۲', { sub: 'نشانی کارخانه را وارد می‌کنیم.' });
  await R.type('div[name=city] input', 'تهران', {});
  await R.type('div[name=phone] input', '021-56234500', { sub: 'و تلفن شرکت را.' });
  await R.type('div[name=vat] input', '411234567890', { sub: 'شناسه‌ی مالیاتی (کد اقتصادی) شرکت؛ در فاکتورهای رسمی و سامانه‌ی مؤدیان لازم است.', step: 2, done: 2 });
  await R.type('div[name=company_registry] input', '54321', { sub: 'و شماره‌ی ثبت شرکت.' });
  await R.view({ sub: 'واحد پول شرکت ریال است و همه‌ی تاریخ‌ها شمسی نمایش داده می‌شوند.', focus: 'div[name=currency_id]', zoom: 1.35, hold: 1.6 });
  await R.click('.o_form_button_save', { sub: 'ذخیره می‌کنیم؛ نام و لوگوی شرکت از همین حالا همه‌جا دیده می‌شود.', wait: 1500, afterHold: 1.6, done: 3,
    afterCam: 'full' });
  // the users
  await R.click(top('کاربران و شرکت'), { sub: 'حالا برای همکاران کاربر می‌سازیم.', step: 3, wait: 600, afterHold: 0.6,
    afterCam: { focus: [700, 0, 740, 260], zoom: 1.35 } });
  await R.click(item('کاربران'), { wait: 1500, newpage: true, afterHold: 0.8 });
  await R.click('.o_list_button_add, .o_control_panel_main_buttons button.o-kanban-button-new', { sub: 'کاربر تازه: حسابدار شرکت.', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.type('div[name=name] input', 'سارا محمدی', { focus: [500, 120, 940, 300], zoom: 1.35 });
  await R.type('div[name=login] input', 'sara', { sub: 'نام کاربری‌ای که با آن وارد سامانه می‌شود.' });
  const priv = async (labels, option, sub) => {
    for (const label of labels) {
      const input = page.locator(`xpath=//label[normalize-space(text())="${label}"]/ancestor::div[contains(@class,"o_wrap_label")]/following-sibling::div[1]//input`).first();
      if (await input.count()) {
        await R.click(input, { sub, wait: 600, afterHold: 0.6, focus: input, zoom: 1.3, afterCam: undefined });
        const opt = page.locator('.o_select_menu_item, .o-dropdown--menu .dropdown-item', { hasText: option }).first();
        await R.click(opt, { wait: 700, afterHold: 0.8 });
        return true;
      }
    }
    console.log('no privilege', labels);
    return false;
  };
  await priv(['حسابداری', 'فاکتور سازی', 'صورتحساب'], 'مدیر', 'در «سطوح دسترسی» به او دسترسی کامل حسابداری می‌دهیم؛ بقیه‌ی بخش‌ها بسته می‌ماند.');
  await R.click('.o_form_button_save', { sub: 'ذخیره؛ سارا فقط بخش‌هایی را می‌بیند که اجازه دارد.', wait: 1500, afterHold: 1.2, done: 4 });
  await R.click('.o_form_button_create, .o_control_panel_main_buttons .o_form_button_create', { sub: 'کاربر بعدی: مسئول انبار و فروش.', step: 4, wait: 1500, newpage: true, afterHold: 0.6 });
  await R.type('div[name=name] input', 'رضا کریمی', { focus: [500, 120, 940, 300], zoom: 1.35 });
  await R.type('div[name=login] input', 'reza', {});
  await priv(['موجودی', 'انبار', 'موجودی کالا'], 'کاربر', 'دسترسی انبار…');
  await priv(['فروش ها', 'فروش'], 'همه', '…و دسترسی فروش.');
  await R.click('.o_form_button_save', { sub: 'ذخیره می‌کنیم.', wait: 1500, afterHold: 1.0 });
  await R.click(page.locator('.o_breadcrumb a, .breadcrumb-item a').first(), { sub: 'هر همکار با نام کاربری و رمز خودش وارد می‌شود و فقط کار خودش را می‌بیند.', wait: 1500, newpage: true, afterHold: 2.4, done: 5 });
  await R.view({ sub: 'شرکت و کاربران آماده شد. بخش بعد: پایه‌ی مالی؛ حساب‌ها، مالیات و بانک.', hold: 2.4 });
};
