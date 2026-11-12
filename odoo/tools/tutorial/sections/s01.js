// Section 1: the address in the browser, the sign-in, the apps, the menus and the search, the dark and light look
module.exports = async (R, page) => {
  // a new tab of the browser
  await page.setContent('<html><body style="margin:0;background:#202124"></body></html>');
  await R.address('aryapack.veronerp.ir', R.B + '/web/login?db=' + R.DB, {
    sub: 'آدرس سامانه‌ی شرکت را در نوار آدرس مرورگر می‌نویسیم.', step: 0 });
  await R.view({ sub: 'صفحه‌ی ورود ERP-VERON باز می‌شود.', hold: 1.6, newpage: true, done: 1 });
  const form = '.oe_login_form';
  await R.type('input[name=login]', 'modir', { sub: 'نام کاربری‌ای را که مدیر سیستم ساخته وارد می‌کنیم.', step: 1,
    focus: form, zoom: 1.35 });
  await R.type('input[name=password]', 'Veron@1405', { sub: 'و رمز عبور را؛ رمز هیچ‌وقت روی صفحه دیده نمی‌شود.', focus: form, zoom: 1.35 });
  await R.click('.oe_login_form button[type=submit]', { sub: 'روی «ورود» می‌زنیم.', focus: form, zoom: 1.35, wait: 2500,
    newpage: true, afterHold: 0.4 });
  await R.view({ sub: 'این صفحه‌ی برنامه‌هاست؛ هر آیکون یکی از بخش‌های شرکت است.', step: 2, hold: 1.6, cam: 'full', done: 2 });
  // all the apps: the page goes down slowly to the last of them, then back up
  const down = await page.evaluate(() => {
    const els = [document.scrollingElement, ...document.querySelectorAll('.o_home_menu, .o_action_manager, .o_web_client *')];
    const el = els.find((e) => e && e.scrollHeight > e.clientHeight + 20 && getComputedStyle(e).overflowY !== 'hidden');
    return el ? el.scrollHeight - el.clientHeight : 0;
  });
  if (down > 40) {
    await R.scroll(down, { sub: 'همه‌ی برنامه‌ها را ببینیم: از فروش و خرید تا منابع انسانی، وب‌سایت و بازاریابی.', dur: Math.min(4.5, 1.2 + down / 300), hold: 1.2 });
    await R.scroll(-down, { dur: Math.min(3, 0.8 + down / 450), hold: 0.4 });
  }
  const app = (xmlid) => page.locator(`.o-app-menu-item[data-menu-xmlid="${xmlid}"]`).first();
  await R.hover(app('sale.sale_menu_root'), { sub: 'فروش، خرید، انبار، تولید، حسابداری و بقیه‌ی بخش‌ها، همه در یک جا.' });
  await R.hover(app('crm.crm_menu_root'), {});
  await R.hover(app('account.menu_finance'), { hold: 0.6 });
  await R.click(app('account.menu_finance'), { sub: 'با یک کلیک وارد هر بخش می‌شویم؛ مثلاً حسابداری.', step: 3, wait: 1800, newpage: true, afterHold: 0.6, done: 3 });
  // the camera on the menus themselves (they start at the right, next to the app's name), never cut at the side
  const menus = ['.o_menu_brand', '.o_menu_sections'];
  await R.view({ sub: 'منوهای بالای صفحه کارهای همان بخش است: مشتریان، تأمین‌کنندگان، گزارش‌ها و پیکربندی.', focus: menus, zoom: 1.3, hold: 1.6 });
  await R.click(page.locator('.o_menu_sections button', { hasText: 'مشتریان' }).first(), { sub: 'هر منو زیرمنوهای خودش را دارد.', focus: menus, zoom: 1.3, wait: 600, afterHold: 1.8,
    afterCam: { focus: ['.o_menu_sections', '.o-dropdown--menu'], zoom: 1.3 } });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  // the button of the apps, in the corner: the camera goes to it and it is marked before the click
  const corner = [1000, 0, 440, 250];
  await R.hover('.o_grid_apps_menu__button', { sub: 'با این دکمه، گوشه‌ی بالای صفحه، به صفحه‌ی برنامه‌ها برمی‌گردیم.', focus: corner, zoom: 1.35, mark: true, hold: 1.4 });
  await R.click('.o_grid_apps_menu__button', { focus: corner, zoom: 1.35, mark: true, wait: 900, newpage: true, afterHold: 0.6 });
  await R.type('.o_grid_apps_menu .search-input input', 'فاکتور', { sub: 'برای پیدا کردن هر صفحه نامش را می‌نویسیم؛ همه‌ی صفحه‌های «فاکتور» پیدا می‌شوند.',
    focus: [300, 40, 840, 330], zoom: 1.3, hold: 2.4, done: 4 });
  await page.keyboard.press('Escape');
  await page.locator('.o_grid_apps_menu .search-input input').fill('');
  await R.settle(500);
  // the look: light, then dark again
  await R.click('.o_user_menu button, .o_user_menu', { sub: 'ظاهر برنامه را از منوی کاربر عوض می‌کنیم.', step: 4, wait: 700,
    focus: [0, 0, 600, 320], zoom: 1.35, afterHold: 1.0, afterCam: { focus: [0, 0, 600, 320], zoom: 1.35 } });
  await R.click(page.locator('.o-dropdown--menu .dropdown-item, .o-dropdown--menu .o-dropdown-item', { hasText: 'حالت تاریک' }).first(),
    { sub: 'حالت روشن، برای کار در روز و نور زیاد.', wait: 3500, newpage: true, afterHold: 2.0 });
  await R.click('.o_user_menu button, .o_user_menu', { sub: 'و دوباره حالت تاریک، که برای چشم آرام‌تر است.', wait: 700,
    focus: [0, 0, 600, 320], zoom: 1.35, afterHold: 0.6, afterCam: { focus: [0, 0, 600, 320], zoom: 1.35 } });
  await R.click(page.locator('.o-dropdown--menu .dropdown-item, .o-dropdown--menu .o-dropdown-item', { hasText: 'حالت تاریک' }).first(),
    { wait: 3500, newpage: true, afterHold: 1.4 });
  await R.view({ sub: 'دستیار هوشمند در همه‌ی صفحه‌ها گوشه‌ی پایین کنار شماست؛ در بخش ۱۶ با آن کار می‌کنیم.',
    focus: [0, 560, 560, 250], zoom: 1.3, hold: 2.2, done: 5 });
  await R.view({ sub: 'ورود و آشنایی تمام شد. بخش بعد: ساخت شرکت و کاربران.', cam: 'full', hold: 2.4 });
};
