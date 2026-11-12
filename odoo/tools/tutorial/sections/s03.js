// Section 3: the Iranian chart of accounts, the VAT, the bank account, the cash box and a cheque book
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('account.menu_finance', { sub: 'پایه‌ی مالی شرکت در برنامه‌ی «حسابداری» تنظیم می‌شود؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.' });
  await R.menu('پیکربندی', 'جدول حساب ها', { sub: 'از منوی «پیکربندی» جدول حساب‌ها را باز می‌کنیم.' });
  await R.view({ sub: 'جدول حساب‌ها بر اساس کدینگ استاندارد ایران آماده است؛ از صندوق و بانک تا درآمد و هزینه.', hold: 1.8,
    focus: [0, 90, 1440, 520], zoom: 1.2 });
  await R.search('بانک', { sub: 'با جست‌وجو هر حساب را پیدا می‌کنیم؛ مثلاً حساب‌های بانک.', done: 1 });
  await R.menu('پیکربندی', 'مالیات ها', { sub: 'مالیات‌ها:', step: 1 });
  await R.view({ sub: 'مالیات بر ارزش افزوده‌ی ۱۰٪ برای خرید و فروش آماده است و روی فاکتورها خودکار حساب می‌شود.', hold: 1.6,
    focus: [0, 90, 1440, 300], zoom: 1.3 });
  await R.click(page.locator('.o_data_row').first(), { sub: 'نرخ و حساب‌های هر مالیات را اینجا می‌بینیم.', wait: 1500, newpage: true, afterHold: 2.0, done: 2 });
  await R.menu('پیکربندی', 'دفترروزنامه', { sub: 'حساب بانکی شرکت در «دفترروزنامه‌ها» تعریف می‌شود.', step: 2 });
  await R.click(page.locator('.o_data_row', { hasText: 'بانک' }).first(), { sub: 'دفتر بانک را باز می‌کنیم.', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.set('name', 'بانک ملت - شعبه ونک', { sub: 'نام بانک و شعبه‌ی حساب شرکت.', focus: [300, 110, 1140, 300], zoom: 1.3 });
  if (await page.locator('div[name=bank_acc_number] input').count()) {
    await R.set('bank_acc_number', '0123456789', { sub: 'و شماره‌ی حساب.' });
  }
  await R.saveForm({ sub: 'ذخیره می‌کنیم.', done: 3 });
  await R.menu('پیکربندی', 'دفترروزنامه', { sub: 'برای پول نقد هم یک صندوق می‌سازیم.', step: 3 });
  await R.create({ sub: 'دفتر تازه:' });
  await R.set('name', 'صندوق دفتر مرکزی', { focus: [300, 110, 1140, 300], zoom: 1.3 });
  await R.select('type', 'نقد', { sub: 'نوع آن را «نقد» انتخاب می‌کنیم.', focus: [300, 110, 1140, 300], zoom: 1.3 });
  await R.saveForm({ sub: 'ذخیره؛ دریافت و پرداخت نقدی از این صندوق ثبت می‌شود.', done: 4 });
  await R.menu('چک‌ها', 'دسته‌چک', { sub: 'و دسته‌چک شرکت، برای پرداخت به تأمین‌کنندگان.', step: 4 });
  await R.create({ sub: 'دسته‌چک تازه:' });
  await R.set('name', 'دسته‌چک ملت ۱۴۰۵', { focus: [200, 110, 1240, 360], zoom: 1.25 });
  await R.many2one('journal_id', 'ملت', { sub: 'بانک آن…' });
  await R.set('first_serial', '100201', { sub: 'شماره‌ی سریال اولین برگ…' });
  await R.set('sheets', '50', { sub: '…و تعداد برگ‌ها.' });
  await R.saveForm({ sub: 'برای هر چکی که می‌کشیم، برگ بعدی خودش پیشنهاد می‌شود.', done: 5, afterHold: 2.0 });
  await R.view({ sub: 'پایه‌ی مالی آماده است. بخش بعد: مخاطبان؛ مشتری‌ها و تأمین‌کنندگان.', cam: 'full', hold: 2.4 });
};
