// Section 17: the manager's dashboards, built from the documents recorded in the sections before
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('spreadsheet_dashboard.spreadsheet_dashboard_menu_root', { sub: 'مدیر شرکت وضعیت را در برنامه‌ی «داشبوردها» می‌بیند.', wait: 2500, hold: 1.4 });
  await R.tourMenus([
    ['داشبورد من', 'منوی «داشبورد من»: داشبورد شخصی هر کاربر.'],
    ['پیکربندی', 'و «پیکربندی»: ساخت و ویرایش داشبوردها، مثل یک صفحه‌گسترده.'],
  ], { step: 0 });
  await R.click(R.topMenu('داشبوردها'), { sub: 'به «داشبوردها» برمی‌گردیم.', wait: 5000, newpage: true, afterHold: 0.8 });
  const side = (t) => page.locator('.o_spreadsheet_dashboard_action, .o_action').getByText(t, { exact: true }).first();
  await R.view({ sub: 'داشبورد فروش: پیش‌فاکتورها، سفارش‌ها و درآمد؛ همان فروش دو دستگاه به آفتاب طلایی.', focus: [80, 120, 920, 120], zoom: 1.3, hold: 2.6 });
  await R.view({ sub: 'نمودار فروش ماهانه و جدول سفارش‌های برتر، همه زنده و از روی سندها.', hold: 2.2, cam: 'full', done: 1 });
  await R.click(side('محصول'), { sub: 'داشبورد «محصول»: کدام دستگاه بیشتر فروش رفته است.', step: 1, wait: 5000, afterHold: 2.4, done: 2 });
  await R.click(side('صدور فاکتور'), { sub: '«صدور فاکتور»: فاکتورهای صادره، مانده‌ی مطالبات و مشتریان بدهکار.', step: 2, wait: 5000, afterHold: 2.6, done: 3 });
  // the period and sharing
  const period = page.locator('.o_control_panel button, .o_control_panel .o-dropdown', { hasText: 'روز گذشته' }).first();
  if (await period.count()) {
    await R.click(period, { sub: 'بازه‌ی زمانی هر داشبورد با یک کلیک عوض می‌شود: هفت روز، سی روز، سه ماه یا سال.', step: 3, wait: 900, afterHold: 2.0,
      afterCam: { focus: [300, 40, 900, 400], zoom: 1.3 } });
    await page.keyboard.press('Escape');
  }
  await R.view({ hold: 0.4, done: 4 });
  const share = page.locator('.o_control_panel button, .o_control_panel a', { hasText: 'اشتراک' }).first();
  if (await share.count()) await R.hover(share, { sub: 'با «اشتراک‌گذاری» نسخه‌ای از داشبورد برای هیئت‌مدیره فرستاده می‌شود.', step: 4, mark: true, hold: 2.2 });
  await R.view({ hold: 0.6, done: 5 });
  await R.view({ sub: 'داشبورد تمام شد. بخش آخر: جمع‌بندی.', cam: 'full', hold: 2.4 });
};
