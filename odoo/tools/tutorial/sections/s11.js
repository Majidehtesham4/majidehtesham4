// Section 11: the customer's cheque received, the invoice settled with it, the cheque deposited and cashed;
// the trial balance and the legal books
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('account.menu_finance', { sub: 'از صفحه‌ی برنامه‌ها «حسابداری» را باز می‌کنیم.', afterSub: 'داشبورد حسابداری: فروش، خرید، بانک و چک‌ها در یک نگاه.', hold: 1.8 });
  await R.tourMenus([
    ['مشتریان', 'منوی «مشتریان»: فاکتورهای فروش و دریافت‌ها.'],
    ['چک‌ها', '«چک‌ها»: چک‌های دریافتنی، پرداختنی و دسته‌چک‌ها.'],
    ['حسابداری ایرانی', '«حسابداری ایرانی»: سند از روی الگو و دفاتر قانونی.'],
    ['گزارش', 'و «گزارش»: دفتر کل، تراز آزمایشی، گزارش ارزش افزوده و گزارش‌های مالی.'],
  ], { step: 0 });
  // the cheque
  await R.menu('چک‌ها', 'چک‌های دریافتنی', { sub: 'آفتاب طلایی بهای دستگاه‌ها را با چک داد؛ آن را ثبت می‌کنیم.' });
  await R.create({});
  await R.many2one('partner_id', 'آفتاب طلایی', { sub: 'مشتری…', pick: 'آفتاب طلایی' });
  await R.set('amount', '10670000000', { sub: '…مبلغ؛ به حروف هم خودکار نوشته می‌شود…' });
  await R.click('div[name=due_date] input', { sub: '…تاریخ سررسید…', wait: 700, afterHold: 0.6 });
  await R.click(page.locator('.o_datetime_picker .o_today, .o_date_item_cell.o_today, .o_datetime_picker button.o_today').first(), { wait: 600, afterHold: 0.6 });
  await R.set('sayad_id', '1234567890123456', { sub: '…شناسه‌ی ۱۶ رقمی صیاد…' });
  await R.set('serial', '845120', { sub: '…و سریال چک.' });
  await R.many2one('bank_journal_id', 'ملت', { sub: 'حسابی که چک به آن واگذار می‌شود: بانک ملت.', pick: 'ملت' });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.click('.o_statusbar_buttons button[name=action_receive]:visible', { sub: '«دریافت»؛ چک «نزد صندوق» است و سند آن خودکار ثبت می‌شود.', wait: 2000, afterHold: 1.6, done: 1 });
  // the invoice settled
  await R.menu('مشتریان', 'فاکتورها', { sub: 'حالا فاکتور فروش را با این چک تسویه می‌کنیم.', step: 1 });
  await R.click(page.locator('.o_data_row', { hasText: 'آفتاب' }).first(), { wait: 1800, newpage: true, afterHold: 0.8 });
  const add = page.locator('div[name=invoice_outstanding_credits_debits_widget] a, div[name=invoice_outstanding_credits_debits_widget] button', { hasText: 'افزودن' }).first();
  await R.view({ sub: 'پایین فاکتور، مبلغ چک به عنوان «اعتبار باز» مشتری آمده است.', focus: 'div[name=invoice_outstanding_credits_debits_widget]', zoom: 1.3, hold: 2.0 });
  if (await add.count()) await R.click(add, { sub: 'با «افزودن» به این فاکتور وصل می‌شود.', wait: 2000, afterHold: 1.0, focus: 'div[name=invoice_outstanding_credits_debits_widget]', zoom: 1.3 });
  await R.view({ sub: 'فاکتور «پرداخت‌شده» شد.', hold: 2.0, done: 2, cam: 'full' });
  // the cheque to the bank
  await R.menu('چک‌ها', 'چک‌های دریافتنی', { sub: 'چک را برای وصول به بانک می‌دهیم.', step: 2 });
  await R.click(page.locator('.o_data_row').first(), { wait: 1800, newpage: true, afterHold: 0.8 });
  await R.click('.o_statusbar_buttons button[name=action_deposit]:visible', { sub: '«واگذاری به بانک»؛ چک «در جریان وصول» است.', wait: 2000, afterHold: 1.4 });
  await R.click('.o_statusbar_buttons button[name=action_cash]:visible', { sub: 'بانک وصول کرد: «وصول»؛ مبلغ به حساب بانک ملت می‌نشیند.', wait: 2000, afterHold: 1.6 });
  await R.view({ sub: 'همه‌ی سندهای چک از دریافت تا وصول، خودکار ثبت شده است.', focus: [0, 100, 1440, 300], zoom: 1.2, hold: 2.0, done: 3 });
  // the trial balance
  await R.menu('گزارش', 'تراز آزمایشی', { sub: 'تراز آزمایشی: مانده‌ی همه‌ی حساب‌ها.', step: 3 });
  await R.view({ sub: 'دوره به طور پیش‌فرض از اول سال مالی تا امروز است.', focus: '.modal-content', zoom: 1.2, hold: 1.8 });
  await R.click(page.locator('.modal-footer button', { hasText: 'نمایش' }).first(), { sub: '«نمایش».', wait: 3500, newpage: true, afterHold: 2.6, done: 4 });
  await R.view({ sub: 'فروش، خرید، انبار، بانک و چک‌ها همه در تراز آمده‌اند؛ بدون حتی یک سند دستی.', hold: 2.4, focus: [0, 60, 1440, 600], zoom: 1.15 });
  // the legal books
  await R.menu('حسابداری ایرانی', 'دفاتر قانونی', { sub: 'و دفاتر قانونی: دفتر روزنامه، دفتر کل و تراز چهارستونی برای چاپ رسمی.', step: 4 });
  await R.view({ focus: '.modal-content', zoom: 1.25, hold: 1.6 });
  const journal = page.locator('.modal div[name=book] .o_radio_item, .modal div[name=book] .form-check', { hasText: 'روزنامه' }).first();
  if (await journal.count()) await R.click(journal.locator('input, label').first(), { sub: 'دفتر روزنامه را انتخاب می‌کنیم؛ دوره‌اش سال مالی جاری است.', wait: 600, afterHold: 1.0, focus: '.modal-content', zoom: 1.25 });
  const print = page.locator('.modal-footer button', { hasText: 'چاپ' }).first();
  await R.hover(print, { sub: 'با «چاپ» فایل PDF دفتر برای پلمب و بایگانی ساخته می‌شود.', mark: true, hold: 2.0, focus: '.modal-content', zoom: 1.25 });
  await page.keyboard.press('Escape');
  await R.view({ sub: 'حسابداری تمام شد. بخش بعد: وب‌سایت و فروشگاه اینترنتی.', cam: 'full', hold: 2.4, done: 5 });
};
