// Section 16: the AI agents: the assistant on every page, an agent's instructions, skills, knowledge and triggers, the
// library of roles, and connecting a service (its key is entered by the system manager; nothing is sent here)
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('veron_ai_agent.menu_root', { sub: 'هوش مصنوعی در برنامه‌ی «ایجنت‌های هوش مصنوعی» است؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.', hold: 1.4 });
  await R.tourMenus([
    ['تأییدها و پرسش‌ها', 'منوی «تأییدها و پرسش‌ها»: هر اقدام حساس ایجنت اینجا منتظر تأیید یک انسان می‌ماند.'],
    ['کار', '«کار»: اجراها، یافته‌های نیازمند بررسی و پیش‌نویس‌ها.'],
    ['پیکربندی', '«پیکربندی»: نقش‌ها، مهارت‌ها، منبع‌های دانش، اتصال هوش مصنوعی و تاریخچه‌ی اقدام‌ها.'],
    ['راهنما', 'و «راهنما»: آموزش کار با ایجنت‌ها.'],
  ], { step: 0 });
  await R.click(R.topMenu('ایجنت‌ها'), { sub: 'به فهرست «ایجنت‌ها» برمی‌گردیم.', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.click(page.locator('.o_kanban_record:not(.o_kanban_ghost)', { hasText: 'دستیار' }).first(), { sub: '«دستیار» ایجنتی است که در همه‌ی صفحه‌ها گوشه‌ی پایین در دسترس است.', wait: 2500, newpage: true, afterHold: 1.2 });
  await R.view({ sub: 'وسط صفحه گفت‌وگو است، با پرسش‌های آماده؛ مثل «کالاهای کم‌موجود» یا «گزارش فروش این ماه».', focus: [440, 560, 660, 240], zoom: 1.3, hold: 2.4 });
  await R.view({ sub: 'ایجنت فقط با ابزارهای خودش و با همان دسترسی کاربر کار می‌کند؛ اقدام‌های حساس منتظر تأیید انسان می‌ماند.', focus: [440, 700, 660, 110], zoom: 1.35, hold: 2.4, done: 1 });
  // instructions, skills, knowledge, triggers
  const tab = (t) => page.locator('.o_action_manager').getByText(t, { exact: true }).first();
  await R.click(tab('دستورالعمل‌ها'), { sub: '«دستورالعمل‌ها»: ایجنت چطور رفتار کند؛ با «ویرایش» عوض می‌شود.', step: 1, wait: 800, afterHold: 1.6, focus: [0, 100, 440, 400], zoom: 1.35 });
  await R.click(tab('مهارت‌ها'), { sub: '«مهارت‌ها» و ابزارها: برای هر ایجنت روشن یا اضافه می‌شود؛ مثل گزارش فروش، پیگیری مطالبات یا موجودی کالا.', wait: 900, afterHold: 1.8, focus: [0, 100, 440, 500], zoom: 1.35 });
  await R.click(tab('دانش'), { sub: '«دانش»: آیین‌نامه‌ها، کاتالوگ و مستندات شرکت را اینجا اضافه می‌کنیم تا ایجنت از آن جواب دهد.', wait: 900, afterHold: 1.8, focus: [0, 100, 440, 500], zoom: 1.35, done: 2 });
  await R.click(tab('راه‌اندازها'), { sub: '«راه‌اندازها»: با «افزودن»، ایجنت خودش در زمان یا رویداد معین کار می‌کند؛ مثلاً هر صبح گزارش مطالبات معوق.', step: 2, wait: 900, afterHold: 2.0, focus: [0, 100, 440, 500], zoom: 1.35, done: 3 });
  // the library of roles
  await R.menu('پیکربندی', 'کتابخانه‌ی نقش‌ها', { sub: 'برای هر بخش شرکت یک ایجنت آماده هست: «کتابخانه‌ی نقش‌ها».', step: 3 });
  await R.view({ sub: 'حسابدار، انباردار، کارشناس فروش، منابع انسانی و…؛ با «ساخت تیم» چند ایجنت با هم ساخته می‌شود.', hold: 2.6, cam: 'full', done: 4 });
  // connecting a service
  await R.menu('پیکربندی', 'اتصال هوش مصنوعی', { sub: 'و اتصال به سرویس هوش مصنوعی.', step: 4 });
  await R.view({ sub: 'سرویس را انتخاب می‌کنیم؛ کلید آن را مدیر سیستم همین‌جا در خود ERP وارد می‌کند و هیچ‌جا نمایش داده نمی‌شود.', hold: 2.8, focus: '.modal-content, .o_form_view', zoom: 1.2 });
  await R.view({ sub: 'خواندن عکس و PDF و تبدیل گفتار به متن، بدون هوش مصنوعی و روی خود سرور هم کار می‌کند.', hold: 2.4, focus: '.modal-content, .o_form_view', zoom: 1.2, done: 5 });
  await page.keyboard.press('Escape');
  await R.view({ sub: 'هوش مصنوعی تمام شد. بخش بعد: داشبورد مدیر.', cam: 'full', hold: 2.4 });
};
