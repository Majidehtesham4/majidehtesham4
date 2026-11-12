// Section 14: a new employee with the contract, the pay and the insurance; the month's payslip by Iran's labour law;
// the insurance and tax lists
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('hr.menu_hr_root', { sub: 'پرونده‌ی کارکنان در برنامه‌ی «کارمندان» است؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.', hold: 1.4 });
  await R.tourMenus([
    ['دپارتمان‌ها', 'منوی «دپارتمان‌ها»: واحدهای شرکت و مدیرانشان.'],
    ['آموزش', '«آموزش»: دوره‌ها و گواهینامه‌های کارکنان.'],
    ['گزارش', '«گزارش»: مهارت‌ها و گواهینامه‌ها.'],
    ['پیکربندی', 'و «پیکربندی»: موقعیت‌های شغلی، برنامه‌های کاری و الگوهای قرارداد.'],
  ], { step: 0 });
  await R.click(R.topMenu('کارمندان'), { sub: 'به فهرست «کارمندان» برمی‌گردیم.', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.create({ sub: 'کارمند تازه‌ی کارگاه مونتاژ.' });
  await R.set('name', 'علی رضایی', {});
  await R.set('job_title', 'تکنسین مونتاژ', { sub: 'عنوان شغل…' });
  await R.set('work_phone', '021-56234512', { sub: '…تلفن محل کار…' });
  await R.many2one('department_id', 'تولید', { sub: '…و دپارتمان؛ «تولید» را همین‌جا می‌سازیم.', pick: 'ایجاد' });
  await R.view({ hold: 0.8, done: 1 });
  // the contract and the pay
  await R.click(page.locator('.o_notebook .nav-link', { hasText: 'حقوق و دستمزد' }).first(), { sub: 'زبانه‌ی «حقوق و دستمزد»: قرارداد و حقوق.', step: 1, wait: 800, afterHold: 0.6 });
  const start = page.locator('div[name=contract_date_start] input').first();
  if (await start.count()) {
    await R.click(start, { sub: 'شروع قرارداد: امروز.', wait: 700, afterHold: 0.6 });
    await R.click(page.locator('.o_datetime_picker .o_today, .o_date_item_cell.o_today, .o_datetime_picker button.o_today').first(), { wait: 600, afterHold: 0.5 });
  }
  await R.set('wage', '180000000', { sub: 'حقوق پایه‌ی ماهانه به ریال…' });
  await R.many2one('struct_id', 'قانون کار', { sub: '…و ساختار حقوق: «قانون کار ایران»؛ حق مسکن، بن، حق اولاد، بیمه و مالیات خودکار حساب می‌شود.', pick: 'قانون کار' });
  const insured = page.locator('div[name=veron_insured] input').first();
  if (await insured.count() && !(await insured.isChecked())) await R.click(insured, { sub: 'کارمند بیمه‌ی تأمین اجتماعی دارد…', wait: 500, afterHold: 0.5 });
  const insNo = page.locator('div[name=veron_insurance_number] input').first();
  if (await insNo.count()) await R.type(insNo, '0012345678', { sub: '…با این شماره‌ی بیمه.' });
  await R.click(page.locator('.o_notebook .nav-link', { hasText: 'سوابق ایرانی' }).first(), { sub: 'زبانه‌ی «سوابق ایرانی»: مشخصات شناسنامه برای دیسکت بیمه.', wait: 800, afterHold: 0.6 });
  await R.set('veron_father_name', 'حسین', {});
  await R.set('veron_id_number', '4521', {});
  await R.saveForm({ sub: 'ذخیره؛ پرونده‌ی کارمند کامل شد.', done: 2 });
  // the payslip
  await R.openApp('payroll.payroll_menu_root', { sub: 'حالا حقوق: برنامه‌ی «حقوق و دستمزد».', step: 2, hold: 1.4 });
  await R.tourMenus([
    ['دسته‌های فیش حقوق', 'منوی «دسته‌های فیش حقوق»: فیش همه‌ی کارکنان یک ماه با هم.'],
    ['منابع انسانی ایران', '«منابع انسانی ایران»: وام و مساعده، مأموریت، دیسکت تأمین اجتماعی، لیست مالیات و فایل بانکی حقوق.'],
    ['پیکربندی', 'و «پیکربندی»: نرخ‌های سالانه و قوانین حقوق.'],
  ]);
  // the year's rates, checked and confirmed by a person before the first payslip
  await R.menu('پیکربندی', 'نرخ‌های سالانه', { sub: 'پیش از اولین فیش سال، نرخ‌های قانونی سال را باز می‌کنیم.' });
  await R.click(page.locator('.o_data_row', { hasText: '1405' }).first(), { wait: 1800, newpage: true, afterHold: 0.8 });
  await R.view({ sub: 'حداقل دستمزد، حق مسکن، بن، حق اولاد، سقف بیمه و پله‌های مالیات؛ مسئول حقوق آن‌ها را با مصوبه‌ی رسمی همان سال مقایسه می‌کند…', hold: 2.8, focus: '.o_form_sheet', zoom: 1.15 });
  const confirmRates = page.locator('.o_statusbar_buttons button[name=action_confirm]:visible').first();
  if (await confirmRates.count()) {
    await R.click(confirmRates, { sub: '…و پس از بررسی «تأیید نرخ‌ها» را می‌زند؛ تا تأیید نشود هیچ فیشی حساب نمی‌شود.', wait: 1500, afterHold: 1.2 });
    const ok = page.locator('.modal .modal-footer button.btn-primary:visible').first();
    if (await ok.count()) await R.click(ok, { wait: 1500, afterHold: 1.2 });
  }
  await R.click(R.topMenu('فیش حقوقی کارکنان'), { sub: 'فیش حقوق تازه:', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.create({});
  await R.many2one('employee_id', 'علی رضایی', { sub: 'کارمند را انتخاب می‌کنیم؛ قرارداد و ساختار حقوقش خودکار می‌آید.', pick: 'علی رضایی' });
  await R.view({ hold: 1.4, done: 3 });
  await R.click('.o_statusbar_buttons button[name=compute_sheet]:visible', { sub: '«برگه‌ی محاسباتی»: حقوق این ماه حساب می‌شود.', step: 3, wait: 2500, afterHold: 1.0 });
  const calc = page.locator('.o_notebook .nav-link', { hasText: 'محاسبه' }).first();
  if (await calc.count()) await R.click(calc, { wait: 800, afterHold: 0.6 });
  await R.view({ sub: 'حقوق پایه، حق مسکن، بن، بیمه‌ی سهم کارمند و مالیات، سطر به سطر؛ این حقوق زیر سقف معافیت سال است و مالیاتش صفر شد.', focus: '.o_notebook', zoom: 1.2, hold: 2.6 });
  const done = page.locator('.o_statusbar_buttons button[name=action_payslip_done]:visible').first();
  if (await done.count()) await R.click(done, { sub: '«تأیید»؛ سند حقوق در حسابداری خودکار ثبت می‌شود.', wait: 2500, afterHold: 1.6 });
  await R.view({ hold: 0.8, done: 4 });
  // the lists for the insurance and the tax
  await R.menu('منابع انسانی ایران', 'دیسکت تأمین اجتماعی', { sub: 'و آخر ماه، دیسکت تأمین اجتماعی…', step: 4 });
  await R.view({ sub: '…فایل دیسکت کارگاه برای سامانه‌ی تأمین اجتماعی از روی فیش‌های همین ماه ساخته می‌شود؛ لیست مالیات حقوق هم همین‌طور.', hold: 2.6, focus: '.modal-content, .o_form_view', zoom: 1.2 });
  await page.keyboard.press('Escape');
  await R.view({ sub: 'منابع انسانی تمام شد. بخش بعد: تأییدها و دبیرخانه.', cam: 'full', hold: 2.4, done: 5 });
};
