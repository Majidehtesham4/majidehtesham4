// Section 15: a purchase request sent for approval and approved; an outgoing letter registered with its number and
// referred to a colleague
module.exports = async (R, page) => {
  await R.login('modir', 'Veron@1405');
  await R.openApp('veron_approval.menu_root', { sub: 'درخواست‌هایی که تأیید می‌خواهند در برنامه‌ی «تأییدیه‌ها» است.', afterSub: 'هر نوع درخواست یک کارت دارد: خرید، پرداخت، مرخصی، وام و عمومی.', hold: 1.8 });
  await R.tourMenus([
    ['درخواست‌های من', 'منوی «درخواست‌های من»: هر چه خودم خواسته‌ام.'],
    ['منتظر تأیید', '«منتظر تأیید»: درخواست‌هایی که منتظر تأیید من است.'],
    ['همه‌ی درخواست‌ها', '«همه‌ی درخواست‌ها»: همه، برای مدیر.'],
    ['پیکربندی', 'و «پیکربندی»: نوع درخواست‌ها، تأییدکنندگان و تعداد تأیید لازم.'],
  ], { step: 0 });
  await R.click(R.topMenu('درخواست جدید'), { sub: 'به «درخواست جدید» برمی‌گردیم.', wait: 1500, newpage: true, afterHold: 0.6 });
  await R.click(page.locator('.o_kanban_record', { hasText: 'درخواست خرید' }).locator('button, a.btn').first(), { sub: 'کارگاه یک دستگاه جوش پلاستیک می‌خواهد: «درخواست جدید» در کارت «درخواست خرید».', wait: 1800, newpage: true, afterHold: 0.8 });
  await R.set('name', 'خرید دستگاه جوش پلاستیک برای خط مونتاژ', { sub: 'موضوع درخواست…' });
  const amount = page.locator('div[name=amount] input').first();
  if (await amount.count() && await amount.isVisible()) await R.type(amount, '850000000', { sub: '…مبلغ تقریبی…' });
  const desc = page.locator('div[name=description] [contenteditable=true]').first();
  if (await desc.count()) await R.type(desc, 'دستگاه فعلی خراب شده و تولید روزانه را کند کرده است.', { sub: '…و دلیل آن.' });
  await R.saveForm({ sub: 'ذخیره.', done: 1 });
  await R.click('.o_statusbar_buttons button[name=action_submit]:visible', { sub: '«ارسال»؛ درخواست برای تأییدکنندگان می‌رود و برایشان کار ثبت می‌شود.', step: 1, wait: 1800, afterHold: 1.6, done: 2 });
  // the approval
  await R.click(R.topMenu('منتظر تأیید'), { sub: 'تأییدکننده (اینجا مدیر شرکت) آن را در «منتظر تأیید» می‌بیند.', step: 2, wait: 1800, newpage: true, afterHold: 1.0 });
  await R.click(page.locator('.o_data_row, .o_kanban_record:not(.o_kanban_ghost)').first(), { wait: 1800, newpage: true, afterHold: 0.8 });
  await R.click('.o_statusbar_buttons button[name=action_approve]:visible', { sub: 'بررسی می‌کند و «تأیید»؛ درخواست‌دهنده خبردار می‌شود و همه‌چیز در تاریخچه می‌ماند.', wait: 1800, afterHold: 2.0, done: 3 });
  // the secretariat
  await R.openApp('veron_secretariat.menu_root', { sub: 'حالا دبیرخانه: نامه‌های وارده و صادره‌ی شرکت.', step: 3, hold: 1.4 });
  await R.tourMenus([['نامه‌ها', 'منوی «نامه‌ها»: همه‌ی نامه‌ها با شماره، تاریخ، طرف نامه و طبقه‌بندی.']]);
  await R.create({ sub: 'نامه‌ی صادره به آفتاب طلایی.' });
  await R.set('subject', 'پیشنهاد قرارداد خدمات پس از فروش', { sub: 'موضوع…' });
  await R.many2one('partner_id', 'آفتاب طلایی', { sub: '…گیرنده…', pick: 'آفتاب طلایی' });
  await R.many2one('signer_id', 'مدیر سیستم', { sub: '…و امضاکننده.', pick: 'مدیر سیستم' });
  await R.type('div[name=body] [contenteditable=true]', 'با سلام؛ پیرو تحویل دو دستگاه VFFS-320، قرارداد یک‌ساله‌ی خدمات پس از فروش و قطعات یدکی به پیوست تقدیم می‌شود.', { sub: 'متن نامه…' });
  await R.set('enclosure', 'دو برگ', { sub: '…و پیوست‌ها.' });
  await R.click(page.locator('.o_notebook .nav-link', { hasText: 'ارجاع' }).first(), { sub: 'در «ارجاع کارمند» نامه را برای پیگیری به همکار ارجاع می‌دهیم.', step: 4, wait: 800, afterHold: 0.6 });
  await R.click(page.locator('div[name=referral_ids] .o_field_x2many_list_row_add a').first(), { wait: 1200, afterHold: 0.4 });
  const box = (await page.locator('.modal:visible').count()) ? '.modal' : '.o_selected_row';
  await R.type(`${box} div[name=user_id] input`, 'رضا', { pick: 'رضا' });
  await R.type(`${box} div[name=instruction] input`, 'جهت پیگیری و اقدام', {});
  if (box === '.modal') await R.click(page.locator('.modal-footer button', { hasText: 'بستن' }).first(), { wait: 1200, afterHold: 0.6 });
  await R.saveForm({ sub: 'ذخیره.' });
  await R.click('.o_statusbar_buttons button[name=action_register]:visible', { sub: '«ثبت در دبیرخانه»؛ شماره‌ی نامه خودکار و به ترتیب سال شمسی داده می‌شود.', wait: 1800, afterHold: 2.0 });
  await R.view({ sub: 'شماره و تاریخ نامه ثبت شد؛ رضا کریمی هم برای پیگیری یک کار دریافت کرد.', focus: [500, 100, 940, 260], zoom: 1.3, hold: 2.2, done: 5 });
  await R.view({ sub: 'تأییدها و دبیرخانه تمام شد. بخش بعد: هوش مصنوعی.', cam: 'full', hold: 2.4 });
};
