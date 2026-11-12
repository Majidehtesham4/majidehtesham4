// Section 18: the whole path of Aria Pack seen once more, from the customer's order to the money and the reports
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.view({ sub: 'هجده بخش را با هم دیدیم؛ حالا همه را یک‌جا مرور می‌کنیم.', hold: 2.0, cam: 'full', newpage: true });
  // the order, its delivery, its invoice and its payment
  await R.openApp('sale.sale_menu_root', { sub: 'سفارش آفتاب طلایی را در «فروش» باز می‌کنیم.', step: 0, hold: 1.0 });
  await R.menu('سفارشات', 'سفارشات', { sub: 'فهرست سفارش‌های فروش.' });
  await R.click(page.locator('.o_data_row', { hasText: 'آفتاب' }).first(), { sub: 'سفارش دو دستگاه VFFS-320…', wait: 2000, newpage: true, afterHold: 1.2 });
  await R.view({ sub: '…تحویل و فاکتورش از دکمه‌های بالای همین سفارش در دسترس است: هر سند به سند بعدی وصل است.', focus: [400, 50, 1040, 120], zoom: 1.3, hold: 2.6, done: 1 });
  // the stock and the manufacturing
  await R.openApp('stock.menu_stock_root', { sub: 'انبار: رسید ورق و سنسور از خرید، تولید دو دستگاه و تحویل به مشتری.', step: 1, hold: 2.4 });
  await R.view({ hold: 0.4, done: 2 });
  // the accounting
  await R.openApp('account.menu_finance', { sub: 'حسابداری: فاکتور خرید و فروش، چک، وصول و حقوق؛ بدون یک سند دستی در دفترها نشست.', step: 2, hold: 2.6 });
  await R.view({ sub: 'و فاکتور فروش برای سامانه‌ی مؤدیان آماده شد.', hold: 1.8, done: 3 });
  // the website
  await R.openApp('website.menu_website_configuration', { sub: 'سایت، فروشگاه اینترنتی و بازاریابی دیجیتال مشتری تازه می‌آورند.', step: 3, wait: 3000, hold: 2.6 });
  await R.view({ hold: 0.4, done: 4 });
  // the end
  await R.click('.o_grid_apps_menu__button, .o_menu_toggle', { sub: 'همه‌ی این کارها در یک برنامه، با تقویم شمسی، قوانین ایران و هوش مصنوعی.', step: 4, wait: 1500, newpage: true, afterHold: 2.6 });
  await R.view({ sub: 'ERP-VERON؛ همراه شرکت شما از اولین سفارش تا رشد.', hold: 2.6, done: 5 });
};
