// Section 12: the website's home page made in the editor (a block, its words, the machine's picture), the machine
// published in the online shop with its picture, and the site as a customer sees it
const path = require('path');
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('website.menu_website_configuration', { sub: 'سایت شرکت در برنامه‌ی «تارنما» ساخته می‌شود؛ از صفحه‌ی برنامه‌ها بازش می‌کنیم.',
    afterSub: 'سایت همین‌جا، داخل ERP دیده و ویرایش می‌شود؛ نشان، تلفن و ایمیل شرکت رویش است.', hold: 2.0 });
  await R.tourMenus([
    ['سایت', 'منوی «سایت»: صفحه‌ها و منوهای سایت.'],
    ['تجارت الکترونیکی', '«تجارت الکترونیکی»: سفارش‌های اینترنتی، سبدهای رهاشده و محصولات فروشگاه.'],
    ['گزارش', '«گزارش»: بازدیدها و فروش آنلاین.'],
    ['پیکربندی', 'و «پیکربندی»: تنظیمات سایت و فروشگاه.'],
  ], { step: 0 });
  const site = () => page.frameLocator('iframe:not(.o_ignore_in_tour):not(.o_add_snippet_iframe)').first();
  const file = path.join(__dirname, '..', 'assets', 'vffs320.png');
  // the editor
  await R.click(page.locator('.o_menu_systray button, .o_menu_systray a', { hasText: 'ویرایش' }).first(), { sub: 'صفحه‌ی اصلی هنوز خالی است؛ «ویرایش» را می‌زنیم.', wait: 5000, afterHold: 1.0,
    afterSub: 'ویرایشگر باز شد: بلوک‌های آماده در کنار صفحه، و خود صفحه.', mark: true });
  await R.view({ hold: 1.4, done: 1 });
  // a block, then its words
  const intro = page.locator('.o_snippet', { hasText: 'معرفی' }).first();
  await R.drag(intro, [860, 200, 4, 4], { sub: 'بلوک «معرفی» را برمی‌داریم و روی صفحه رها می‌کنیم.', step: 1, wait: 2500, afterHold: 0.8 });
  await R.view({ sub: 'از میان طرح‌های آماده یکی را انتخاب می‌کنیم.', hold: 1.2 });
  await R.click(page.frameLocator('.modal iframe.o_add_snippet_iframe').locator('.o_snippet_preview_wrap').nth(3), { wait: 3000, afterHold: 1.0, afterCam: 'full' });
  await R.type(site().locator('#wrap h1, #wrap h2').first(), 'ماشین‌آلات بسته‌بندی آریا پک', { line: true, sub: 'عنوان را می‌نویسیم…', cam: 'full' });
  await R.type(site().locator('#wrap p').first(), 'طراحی و ساخت دستگاه‌های بسته‌بندی عمودی، پرکن و شیرینک‌پک؛ با نصب، آموزش و خدمات پس از فروش در سراسر ایران.',
    { line: true, sub: '…و معرفی کوتاه شرکت.', cam: 'full' });
  await R.view({ hold: 1.2, done: 2 });
  // the machine's picture in the block
  await R.click(site().locator('#wrap img').first(), { dbl: true, sub: 'عکس بلوک را با عکس دستگاه عوض می‌کنیم: دو بار کلیک روی عکس.', step: 2, wait: 2200, afterHold: 0.8, afterCam: 'full' });
  await R.chooseFile(page.locator('.modal button:visible', { hasText: 'بارگذاری' }).first(), file, {
    sub: '«یک تصویر را بارگذاری کنید»…', dialogSub: '…و عکس دستگاه را از رایانه انتخاب می‌کنیم.', others: ['catalog-1405.pdf', 'logo.png', 'team.jpg'], afterHold: 1.2 });
  if (await page.locator('.modal:visible').count()) {
    const img = page.locator('.modal .o_existing_attachment_cell, .modal .o_we_attachment_highlight').first();
    if (await img.count()) await R.click(img, { wait: 2500, afterHold: 1.0 });
  }
  await R.view({ sub: 'عکس دستگاه در صفحه نشست.', hold: 1.6 });
  await R.click(page.locator('button[data-action=save]').first(), { sub: '«ذخیره»؛ صفحه‌ی اصلی سایت آماده است.', wait: 5000, afterHold: 2.0, done: 3, afterCam: 'full' });
  // the machine in the shop
  await R.menu('تجارت الکترونیکی', 'محصولات', { sub: 'حالا دستگاه را در فروشگاه اینترنتی منتشر می‌کنیم.', step: 3 });
  await R.click('.o_searchview_facet .o_facet_remove', { sub: 'این فهرست فقط منتشرشده‌ها را نشان می‌دهد؛ فیلتر را برمی‌داریم.', wait: 1200, afterHold: 0.8 });
  await R.search('VFFS', { cam: 'full', afterHold: 1.0 });
  await R.click(page.locator('.o_kanban_record:not(.o_kanban_ghost), .o_data_row').first(), { wait: 2200, newpage: true, afterHold: 0.8 });
  await R.hover('div[name=image_1920]', { sub: 'اول عکس کالا؛ روی جای عکس…', hold: 0.6 });
  await R.chooseFile('div[name=image_1920] .o_select_file_button', file, { sub: '…«ویرایش».', dialogSub: 'عکس دستگاه را انتخاب می‌کنیم.', others: ['catalog-1405.pdf', 'logo.png', 'team.jpg'], afterHold: 1.4 });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.click(page.locator('.oe_button_box button, .o-form-buttonbox button', { hasText: 'تارنما' }).first(), { sub: '«برو به تارنما»: صفحه‌ی همین کالا در سایت.', wait: 5000, newpage: true, afterHold: 1.4 });
  const pub = page.locator('.o_menu_systray').getByText('منتشر نشده').first();
  await R.click(pub, { sub: 'کالا هنوز «منتشر نشده» است؛ با یک کلیک برای همه منتشر می‌شود.', wait: 1800, afterHold: 1.6, done: 4 });
  // the site as a customer sees it
  await R.click(site().locator('header a', { hasText: 'فروشگاه' }).first(), { sub: 'حالا فروشگاه را از چشم مشتری می‌بینیم.', step: 4, wait: 4000, newpage: true, afterHold: 1.8 });
  await R.view({ sub: 'دستگاه با عکس و قیمت در فروشگاه است.', hold: 1.6 });
  await R.click(site().locator('a', { hasText: 'VFFS-320' }).first(), { sub: 'مشتری آن را باز می‌کند…', wait: 3500, newpage: true, afterHold: 1.6 });
  const cart = site().locator('#add_to_cart, a#add_to_cart, button#add_to_cart').first();
  if (await cart.count() && await cart.isVisible()) {
    await R.click(cart, { sub: '…و به سبد خرید اضافه می‌کند؛ سفارش اینترنتی مستقیم در «فروش» ثبت می‌شود.', wait: 3000, afterHold: 2.0, done: 5 });
  } else await R.view({ hold: 2.0, done: 5 });
  await R.view({ sub: 'سایت و فروشگاه آماده است. بخش بعد: بازاریابی دیجیتال؛ ایمیل، پیامک و شبکه‌های اجتماعی.', cam: 'full', hold: 2.4 });
};
