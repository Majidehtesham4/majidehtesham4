// Section 13: an email campaign with its design and words, a post for the Bale and Telegram channels, WhatsApp, and an
// automatic campaign with an SMS and a follow-up; nothing is sent (sending is pointed at)
const path = require('path');
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  const file = path.join(__dirname, '..', 'assets', 'vffs320.png');
  // the email campaign
  await R.openApp('mass_mailing.mass_mailing_menu_root', { sub: 'اول ایمیل: برنامه‌ی «بازاریابی ایمیل» را باز می‌کنیم.', afterSub: 'همه‌ی ارسال‌های ایمیلی با آمار باز شدن و کلیک اینجاست.', hold: 1.6 });
  await R.tourMenus([
    ['لیست‌های پستی', 'منوی «لیست‌های پستی»: فهرست مشترکان خبرنامه.'],
    ['گزارش', '«گزارش»: تحلیل ارسال‌ها و انصراف از دریافت.'],
    ['پیکربندی', 'و «پیکربندی»: تنظیمات، پیگیری لینک‌ها و فهرست سیاه.'],
  ], { step: 0 });
  await R.create({ sub: 'یک ایمیل تازه برای معرفی دستگاه.' });
  await R.set('subject', 'معرفی دستگاه بسته‌بندی عمودی VFFS-320', { sub: 'موضوع ایمیل…' });
  await R.view({ sub: 'گیرندگان: خبرنامه‌ی مشتریان.', focus: [500, 170, 940, 120], zoom: 1.3, hold: 1.4, done: 1 });
  await R.click(page.locator('.o_mail_theme_selector').getByText('خبرنامه‌ی آریا پک').first(), { sub: 'قالب خبرنامه‌ی شرکت را انتخاب می‌کنیم؛ نشان و رنگ‌های آریا پک در آن است…', step: 1, wait: 3500, afterHold: 1.2 });
  const mail = () => page.frameLocator('iframe:visible').last();
  await R.type(mail().locator('h1, h2').first(), 'دستگاه بسته‌بندی عمودی VFFS-320', { line: true, sub: '…و عنوان و متن آن را می‌نویسیم.', cam: 'full' });
  await R.type(mail().locator('p').first(), 'شصت بسته در دقیقه، برای چای، حبوبات و تنقلات؛ با نصب و آموزش رایگان.', { line: true, cam: 'full' });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.hover('.o_statusbar_buttons button[name=action_test]:visible', { sub: 'با «تست» نمونه‌ای اول برای خودمان فرستاده می‌شود…', mark: true, hold: 1.4 });
  await R.hover('.o_statusbar_buttons button[name=action_launch]:visible', { sub: '…و با «ارسال» برای همه‌ی مشترکان؛ باز شدن و کلیک هر ایمیل در گزارش دیده می‌شود.', mark: true, hold: 2.0, done: 2 });
  // the social networks
  await R.openApp('veron_social.menu_root', { sub: 'حالا شبکه‌های اجتماعی: برنامه‌ی «انتشار در شبکه‌ها».', step: 2, hold: 1.4 });
  await R.tourMenus([
    ['پست‌ها', 'منوی «پست‌ها»: همه‌ی پست‌ها، منتشرشده یا زمان‌بندی‌شده.'],
    ['کانال‌ها', '«کانال‌ها»: کانال‌های بله، ایتا و تلگرام شرکت.'],
  ]);
  await R.create({ sub: 'کانال بله‌ی شرکت را اضافه می‌کنیم.' });
  await R.set('name', 'کانال بله آریا پک', {});
  await R.select('platform', 'بله', { sub: 'پیام‌رسان: بله…' });
  await R.set('chat_id', '@aryapack', { sub: '…و نشانی کانال.' });
  const token = page.locator('div[name=token]').first();
  if (await token.count()) await R.hover(token, { sub: 'توکن ربات را مدیر سیستم جداگانه و امن وارد می‌کند؛ هیچ‌جا نمایش داده نمی‌شود.', mark: true, hold: 1.8 });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.click(R.topMenu('پست‌ها'), { sub: 'و پست تازه:', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.create({});
  await R.set('message', 'دستگاه بسته‌بندی عمودی VFFS-320 آماده‌ی تحویل است؛ برای مشاوره با ۰۲۱-۵۶۲۳۴۵۰۰ تماس بگیرید.', { sub: 'متن پست…' });
  await R.hover('div[name=image]', { sub: '…عکس دستگاه…', hold: 0.5 });
  await R.chooseFile('div[name=image] .o_select_file_button', file, { dialogSub: 'عکس را از رایانه انتخاب می‌کنیم.', others: ['catalog-1405.pdf', 'logo.png'], afterHold: 1.2 });
  await R.type('div[name=account_ids] input', 'بله', { sub: '…و کانال‌هایی که در آن منتشر می‌شود.', pick: 'بله' });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.hover('.o_statusbar_buttons button[name=action_post_now]:visible', { sub: 'با «انتشار الان» در همه‌ی کانال‌ها منتشر می‌شود؛ یا با «زمان‌بندی» در ساعت دلخواه.', mark: true, hold: 2.2, done: 3 });
  // WhatsApp
  await R.openApp('veron_whatsapp.menu_root', { sub: 'واتس‌اپ هم برنامه‌ی خودش را دارد.', step: 3, hold: 1.2 });
  await R.tourMenus([
    ['پیام ها', 'منوی «پیام‌ها»: پیام‌های رفته و رسیده؛ هر پیام روی کارت مشتری هم می‌ماند.'],
    ['پیکربندی', 'و «پیکربندی»: شماره‌ها و قالب‌های پیام تأییدشده‌ی واتس‌اپ.'],
  ]);
  await R.view({ hold: 0.8, done: 4 });
  // the automatic campaign, with an SMS
  await R.openApp('veron_marketing_automation.menu_root', { sub: 'و بازاریابی خودکار: پیامک و پیگیری، خودکار و مرحله به مرحله.', step: 4, hold: 1.2 });
  await R.tourMenus([
    ['کمپین‌ها', 'منوی «کمپین‌ها»: هر کمپین چند مرحله دارد.'],
    ['مرحله‌های انجام‌شده', '«مرحله‌های انجام‌شده»: هر پیام و کاری که برای هر مخاطب انجام شد.'],
  ]);
  await R.click(R.topMenu('کمپین‌ها'), { sub: 'به «کمپین‌ها» برمی‌گردیم.', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.create({ sub: 'کمپین تازه: پیگیری بازدیدکنندگان نمایشگاه.' });
  await R.set('name', 'پیگیری بازدیدکنندگان نمایشگاه', {});
  const step = async (name, kind, delay, sub, fill) => {
    await R.click(page.locator('div[name=activity_ids] .o_field_x2many_list_row_add a').first(), { sub, wait: 1500, afterHold: 0.6, afterCam: { focus: '.modal-content', zoom: 1.25 } });
    const m = { focus: '.modal-content', zoom: 1.25 };
    await R.type('.modal div[name=name] input', name, m);
    await R.select('kind', kind, m);
    if (delay) await R.type('.modal div[name=delay_count] input', String(delay), m);
    if (fill) await fill(m);
    await R.click(page.locator('.modal-footer button', { hasText: 'بستن' }).first(), { wait: 1200, afterHold: 0.8 });
  };
  await step('پیامک تشکر', 'پیامک', 0, 'مرحله‌ی اول: همان روز یک پیامک تشکر.', async (m) => {
    await R.type('.modal div[name=sms_body] textarea', 'سلام {{ object.name }}؛ از بازدیدتان از غرفه‌ی آریا پک سپاسگزاریم.', { sub: 'نام هر مخاطب خودکار در پیامک می‌نشیند؛ از پنل پیامک ایرانی (کاوه‌نگار، ملی‌پیامک و…) فرستاده می‌شود.', ...m });
  });
  await step('تماس کارشناس فروش', 'کار', 3, 'مرحله‌ی دوم: سه روز بعد، تماس کارشناس فروش.', async (m) => {
    const todo = page.locator('.modal div[name=todo_summary] input').first();
    if (await todo.count()) await R.type(todo, 'تماس و پیشنهاد دمو', m);
  });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.hover('.o_statusbar_buttons button[name=action_start]:visible', { sub: 'با «شروع»، کمپین برای هر مخاطب خودکار جلو می‌رود.', mark: true, hold: 2.0, done: 5 });
  await R.view({ sub: 'بازاریابی دیجیتال تمام شد. بخش بعد: منابع انسانی و حقوق و دستمزد.', cam: 'full', hold: 2.4 });
};
