# قابلیت‌های دستیار

این صفحه از `iran_erp/commands/capabilities.py` ساخته می‌شود.

## مانده حساب مشتری، تأمین‌کننده یا یک حساب (`balance`)

- نوع: فقط خواندنی
- ابزار: accounts.balance → erpnext get_balance_on; General Ledger
- پیش‌فرض: today
- سؤال فقط وقتی: several parties with the name are listed
- پاسخ: who owes whom, and the side of the account in the company's books (بدهکار/بستانکار)
- لینک: the party's General Ledger, their unpaid invoices
- معیار موفقیت: the ledger balance, with the company's point of view said
- جزئیات: `party` (a customer, supplier or account)
- دسترسی لازم: GL Entry
- نمونه درخواست‌ها:
  - «مانده حساب {party}»
  - «{party} چقدر به ما بدهکاره»
  - «بدهی {party} چقدره»
  - «طلب ما از {party}»
  - «حساب {party} چقدره»
  - «مانده {party}»

## ریز حساب (صورتحساب) مشتری یا تأمین‌کننده (`party_statement`)

- نوع: فقط خواندنی
- ابزار: accounts.party_statement → GL Entry; reports General Ledger, Customer/Supplier Ledger Summary
- پیش‌فرض: this Jalali year; «مشتریان» or «همه»: every customer
- سؤال فقط وقتی: no party and no «همه»: asks which, with «همه» as an answer
- پاسخ: movements and balance (Dr: they owe us)
- لینک: General Ledger of the party, or Customer Ledger Summary
- معیار موفقیت: «همه» runs every customer's statement without asking again
- جزئیات: `party` (a customer or supplier, or «همه»)، `period` (a period)
- دسترسی لازم: GL Entry
- نمونه درخواست‌ها:
  - «صورتحساب مشتریان رو بیار»
  - «صورتحساب همه مشتری‌ها»
  - «ریز حساب همه مشتریان»
  - «گردش حساب مشتری‌ها»
  - «صورتحساب تامین کنندگان»
  - «ریز حساب {party}»

## کل مطالبات از مشتری‌ها و بزرگ‌ترین بدهکاران (`receivables`)

- نوع: فقط خواندنی
- ابزار: accounts.receivables → GL Entry balances of customers; report Accounts Receivable
- پیش‌فرض: every customer, today
- سؤال فقط وقتی: never
- پاسخ: total owed by customers and the largest balances
- لینک: Accounts Receivable report
- معیار موفقیت: customers' balances from the ledger
- دسترسی لازم: GL Entry
- نمونه درخواست‌ها:
  - «کل مطالبات»
  - «جمع طلب از مشتری‌ها»
  - «مشتری‌ها جمعا چقدر بدهکارن»
  - «کل بدهی مشتریان»
  - «حساب‌های دریافتنی»
  - «مانده دریافتنی‌ها»

## آخرین فاکتورهای فروش (همه یا یک مشتری) (`last_sales_invoices`)

- نوع: فقط خواندنی
- ابزار: selling.last_sales_invoices → Sales Invoice
- پیش‌فرض: every customer, the latest 10 drafts and submitted invoices
- سؤال فقط وقتی: never
- پاسخ: a table of invoices with customer, date, total and status
- لینک: the Sales Invoice list with the same filters
- معیار موفقیت: invoices from the ERP; an empty period is said, not «nothing found» for no period
- جزئیات: `customer` (a customer)، `period` (a period)، `limit` (how many)
- دسترسی لازم: Sales Invoice
- نمونه درخواست‌ها:
  - «آخرین فاکتورهای فروش»
  - «فاکتورهای فروش اخیر»
  - «فاکتورهای {customer}»
  - «۵ فاکتور آخر»
  - «فاکتورهای امروز»
  - «فاکتورهای فروش {customer}»

## صدور فاکتور فروش (پیش‌نویس) (`create_sales_invoice`)

- نوع: پیش‌نویس
- ابزار: selling.create_sales_invoice → Sales Invoice (draft)
- پیش‌فرض: today, the default warehouse and price list
- سؤال فقط وقتی: customer and items when missing; whether VAT applies
- پاسخ: the draft with its total
- لینک: the draft invoice, to review and submit in the ERP
- معیار موفقیت: a draft only; never submitted from the chat
- جزئیات: `customer` (customer)، `items` (items, quantities, prices)، `vat` (VAT or not)
- دسترسی لازم: Sales Invoice (create)
- نمونه درخواست‌ها:
  - «برای {customer} فاکتور بزن»
  - «فاکتور فروش برای {customer} {items}»
  - «{items} به {customer} فروختیم»
  - «صدور فاکتور برای {customer}»
  - «فاکتور جدید برای {customer} با {items}»
  - «یک فاکتور فروش بساز»

## موجودی یک کالا یا یک انبار (`stock_balance`)

- نوع: فقط خواندنی
- ابزار: stock.stock_balance → Bin; report Stock Balance / Stock Ledger
- پیش‌فرض: nothing named: every warehouse (a dealership: the cars in the lot)
- سؤال فقط وقتی: never; several items with one name are listed to choose from
- پاسخ: quantity per warehouse, or the most valuable items
- لینک: Stock Ledger of the item, or Stock Balance
- معیار موفقیت: real stock figures
- جزئیات: `item` (an item)، `warehouse` (a warehouse)
- دسترسی لازم: Bin
- نمونه درخواست‌ها:
  - «موجودی کالاها»
  - «موجودی انبار رو بده»
  - «موجودی {item}»
  - «از {item} چند تا داریم»
  - «{item} چقدر تو انبار هست»
  - «موجودی انبار {item}»

## ساختن نام کاربری و رمز برای سرمایه‌گذار (`create_investor_login`)

- نوع: پیش‌نویس
- ابزار: admin.create_investor_login → users.investor_login (User with the Investor role, switched off)
- پیش‌فرض: none
- سؤال فقط وقتی: which investor, the username and the password when not said
- پاسخ: the login prepared, switched off; the password is never repeated
- لینک: the user's form, to check and tick «Enabled»
- معیار موفقیت: a switched-off login linked to the investor; changing an existing login asks yes first
- جزئیات: `investor` (the investor)، `username` (username)، `password` (password the operator gives)
- دسترسی لازم: User (System Manager or Accounts Manager)
- نمونه درخواست‌ها:
  - «برای سرمایه گذار {investor} دسترسی درست کن»
  - «میتونی برای یک سرمایه گذار دسترسی درست کنی بتونه با یوزر نیم و پسورد لوگین کنه»
  - «دسترسی ورود برای سرمایه گذار»
  - «سرمایه گذار {investor} بتونه وارد سیستم بشه»
  - «یوزر و پسورد برای سرمایه گذار {investor} بساز»
  - «برای سرمایه گذار نام کاربری و رمز بساز»

## ساختن کاربر برای همکار یا مشتری (پذیرش، فروشنده، حسابدار، مدیر شعبه، مدیر کل، مشتری) (`create_user_login`)

- نوع: پیش‌نویس
- ابزار: admin.create_user_login → users.create_user (roles by what the person does), switched off
- پیش‌فرض: the only branch, when there is one
- سؤال فقط وقتی: what the person does (it decides the roles), then whatever else is missing
- پاسخ: the login prepared, switched off; the password is never repeated
- لینک: the user's form, to check the roles and tick «Enabled»
- معیار موفقیت: a switched-off login with the roles of its kind
- جزئیات: `kind` (what they do)، `name` (full name)، `username` (username)، `password` (password)، `branch` (branch)
- دسترسی لازم: User (System Manager)
- نمونه درخواست‌ها:
  - «یک کاربر جدید بساز»
  - «برای {name} نقش کاربری با نام کاربری و رمز تعریف کن»
  - «برای {name} کاربر با نقش حسابدار تعریف کن»
  - «برای کارمندم کاربر بساز»
  - «کاربر حسابدار بساز به اسم {name}»
  - «یه یوزر برای فروشنده جدید درست کن»

## عوض کردن رمز عبور یک کاربر (`set_user_password`)

- نوع: تغییر با تأیید
- ابزار: admin.set_user_password → users.set_password
- پیش‌فرض: none
- سؤال فقط وقتی: which login and the password when not said; asks yes before changing
- پاسخ: done, without repeating the password
- لینک: the user's form
- معیار موفقیت: changed only after yes
- جزئیات: `user` (a login by name, username or email)، `password` (the new password)
- دسترسی لازم: User (System Manager)
- نمونه درخواست‌ها:
  - «رمز کاربر {user} رو عوض کن»
  - «پسورد {user} رو بذار»
  - «رمز عبور {user} رو تغییر بده»
  - «برای {user} رمز جدید بذار»
  - «رمز {user} یادش رفته رمز جدید بده»
  - «ریست پسورد {user}»

## اطلاعات و وضعیت یک سرمایه‌گذار (یا همه‌ی سرمایه‌گذاران) (`investor_info`)

- نوع: فقط خواندنی
- ابزار: insight.investor_info → Iran Investor, Iran Investment Contract, investor_portal.get_my_account
- پیش‌فرض: no name: every investor with their active capital
- سؤال فقط وقتی: several investors match the name: they are listed to choose from
- پاسخ: the investor's details, capital, profit to date, what is still owed, next payment, contracts
- لینک: the investor's file, their account page, their contracts
- معیار موفقیت: the named investor's real record; never a login or an invoice
- جزئیات: `investor` (an investor by name or code)، `name` (a name typed that is not on record)
- دسترسی لازم: Iran Investor، Iran Investment Contract
- نمونه درخواست‌ها:
  - «یک سرمایه‌گذار داریم به نام {name} اطلاعاتشو بیار»
  - «اطلاعات سرمایه گذار {investor}»
  - «مشخصات سرمایه گذار {investor} رو بده»
  - «وضعیت سرمایه گذاری {investor}»
  - «سرمایه گذار {investor} رو نشون بده»
  - «{investor} چقدر سرمایه گذاشته»

## موجودی خودروهای نمایشگاه (تعداد، وضعیت، مالک، قیمت) (`car_stock`)

- نوع: فقط خواندنی
- ابزار: insight.car_stock → Iran Vehicle (in the lot: awaiting delivery, in preparation, ready, reserved)
- پیش‌فرض: every branch and owner, cars still in the lot
- سؤال فقط وقتی: never
- پاسخ: count by status, owner and branch, total asking price, the newest cars
- لینک: the car list with the same filters, the dealership dashboard
- معیار موفقیت: the cars of the lot with the filters said
- جزئیات: `branch` (a branch)، `ownership` (امانی / خود نمایشگاه / سرمایه‌گذار in the words)، `status` (آماده فروش)
- دسترسی لازم: Iran Vehicle
- نمونه درخواست‌ها:
  - «موجودی خودرو رو بهم بده»
  - «موجودی ماشین ها»
  - «چند تا ماشین داریم»
  - «خودروهای نمایشگاه»
  - «ماشین های موجود رو بیار»
  - «لیست خودروهای موجود»

## بقیه‌ی دستورها

- سلام و احوالپرسی (`greet`، فقط خواندنی)
- تشکر (`thanks`، فقط خواندنی)
- راهنما و فهرست دستورها (`help`، فقط خواندنی)
- کارهای من (منتظر تأیید، پیش‌نویس‌ها، یادآوری‌ها) (`my_tasks`، فقط خواندنی)
- تاریخ امروز (`today`، فقط خواندنی)
- تبدیل تاریخ شمسی و میلادی (`convert_date`، فقط خواندنی)
- نوشتن مبلغ به حروف (برای چک و قرارداد) (`number_to_words`، فقط خواندنی)
- حساب مالیات بر ارزش افزوده یک مبلغ (`vat_calc`، فقط خواندنی)
- آموزش یک بخش یا سند (چیست و چطور کار می‌کند) (`explain_page`، فقط خواندنی)
- باز کردن فهرست یک نوع سند (مشتری‌ها، فاکتورها، کالاها، ...) (`open_list`، باز کردن صفحه)
- باز کردن فرم خالی برای سند جدید (`new_document`، پیش‌نویس)
- باز کردن گزارش (دفتر کل، تراز، سود و زیان، کاردکس، ...) (`open_report`، باز کردن صفحه)
- باز کردن یک سند با شماره‌اش (`open_document`، باز کردن صفحه)
- نسخه‌ی چاپی یک سند (`print_document`، باز کردن صفحه)
- جستجو در مشتری‌ها، تأمین‌کننده‌ها و کالاها (`search`، فقط خواندنی)
- موجودی صندوق و بانک‌ها (`cash_position`، فقط خواندنی)
- کل بدهی به تأمین‌کننده‌ها و بزرگ‌ترین بستانکاران (`payables`، فقط خواندنی)
- فاکتورهای فروش معوق (سررسید گذشته) (`overdue_sales`، فقط خواندنی)
- فاکتورهای خرید پرداخت‌نشده و معوق (`overdue_purchases`، فقط خواندنی)
- سود و زیان (درآمد، هزینه، سود خالص) (`profit_loss`، فقط خواندنی)
- هزینه‌ها و بزرگ‌ترین سرفصل‌های هزینه (`expenses`، فقط خواندنی)
- مالیات بر ارزش افزوده‌ی دوره (فروش، خرید، پرداختنی) (`vat_report`، فقط خواندنی)
- دریافتی‌های یک دوره (`payments_received`، فقط خواندنی)
- پرداختی‌های یک دوره (`payments_made`، فقط خواندنی)
- ثبت دریافت وجه از مشتری (پیش‌نویس) (`receive_payment`، پیش‌نویس)
- ثبت پرداخت به تأمین‌کننده (پیش‌نویس) (`make_payment`، پیش‌نویس)
- سند حسابداری دستی و ثبت هزینه (با هوش مصنوعی) (`journal_entry`، پیش‌نویس)
- ساخت سال مالی شمسی (`create_fiscal_year`، پیش‌نویس)
- جمع فروش یک دوره (برای همه یا یک مشتری) (`sales_total`، فقط خواندنی)
- مشتری‌های برتر (`top_customers`، فقط خواندنی)
- کالاهای پرفروش (`top_items`، فقط خواندنی)
- فروش یک کالا (`item_sales`، فقط خواندنی)
- مبلغ و وضعیت یک فاکتور (`invoice_info`، فقط خواندنی)
- صدور پیش‌فاکتور (پیش‌نویس) (`create_quotation`، پیش‌نویس)
- ثبت سفارش فروش (پیش‌نویس) (`create_sales_order`، پیش‌نویس)
- سفارش‌های فروش تحویل‌نشده یا فاکتورنشده (`pending_sales_orders`، فقط خواندنی)
- پیش‌فاکتورهای باز (`open_quotations`، فقط خواندنی)
- حواله‌های خروج فاکتورنشده (`unbilled_deliveries`، فقط خواندنی)
- برگشت از فروش (مرجوعی‌ها) (`sales_returns`، فقط خواندنی)
- تعریف مشتری جدید (`create_customer`، پیش‌نویس)
- اطلاعات تماس و مشخصات مشتری یا تأمین‌کننده (`party_info`، فقط خواندنی)
- تعداد مشتری‌ها و مشتری‌های جدید (`customer_count`، فقط خواندنی)
- قیمت فروش و خرید یک کالا (`item_price`، فقط خواندنی)
- تغییر قیمت فروش یک کالا (`set_item_price`، تغییر با تأیید)
- جمع خرید یک دوره (برای همه یا یک تأمین‌کننده) (`purchases_total`، فقط خواندنی)
- تأمین‌کننده‌های اصلی (`top_suppliers`، فقط خواندنی)
- آخرین فاکتورهای خرید (`last_purchase_invoices`، فقط خواندنی)
- ثبت فاکتور خرید (پیش‌نویس) (`create_purchase_invoice`، پیش‌نویس)
- ثبت سفارش خرید (پیش‌نویس) (`create_purchase_order`، پیش‌نویس)
- سفارش‌های خرید دریافت‌نشده (`pending_purchase_orders`، فقط خواندنی)
- تعریف تأمین‌کننده‌ی جدید (`create_supplier`، پیش‌نویس)
- درخواست‌های کالای باز (`material_requests`، فقط خواندنی)
- ثبت درخواست خرید کالا (پیش‌نویس) (`create_material_request`، پیش‌نویس)
- ارزش ریالی موجودی انبار (`stock_value`، فقط خواندنی)
- کالاهای رو به اتمام و تمام‌شده (`low_stock`، فقط خواندنی)
- مشخصات یک کالا (`item_info`، فقط خواندنی)
- تعریف کالای جدید (`create_item`، پیش‌نویس)
- رسید ورود کالا به انبار (پیش‌نویس) (`stock_receipt`، پیش‌نویس)
- خروج یا مصرف کالا از انبار (پیش‌نویس) (`stock_issue`، پیش‌نویس)
- انتقال کالا بین انبارها (پیش‌نویس) (`stock_transfer`، پیش‌نویس)
- گردش (کاردکس) یک کالا (`item_movements`، فقط خواندنی)
- چک‌های نزدیک سررسید (دریافتی و پرداختی) (`cheques_due`، فقط خواندنی)
- چک‌های دریافتی در جریان (`cheques_received`، فقط خواندنی)
- چک‌های پرداختی پاس‌نشده (`cheques_issued`، فقط خواندنی)
- چک‌های برگشتی (`bounced_cheques`، فقط خواندنی)
- ثبت چک دریافتی (پیش‌نویس) (`register_received_cheque`، پیش‌نویس)
- ثبت چک پرداختی (پیش‌نویس) (`register_issued_cheque`، پیش‌نویس)
- وضعیت یک چک (`cheque_info`، فقط خواندنی)
- ثبت سرنخ (مشتری بالقوه) (`create_lead`، پیش‌نویس)
- سرنخ‌های اخیر (`leads`، فقط خواندنی)
- فرصت‌های فروش باز (`opportunities`، فقط خواندنی)
- یادآوری و کار جدید برای خودم (`create_todo`، پیش‌نویس)
- یادآوری‌ها و کارهای باز من (`my_todos`، فقط خواندنی)
- وضعیت پروژه‌ها (`projects`، فقط خواندنی)
- وظایف عقب‌افتاده‌ی پروژه‌ها (`overdue_tasks`، فقط خواندنی)
- دستورهای تولید باز (`work_orders`، فقط خواندنی)
- ثبت دستور تولید (پیش‌نویس) (`create_work_order`، پیش‌نویس)
- مواد اولیه (BOM) یک کالا (`bom_info`، فقط خواندنی)
- میزان تولید یک دوره (`production_total`، فقط خواندنی)
- کارکنان و اطلاعات تماس آن‌ها (`employees`، فقط خواندنی)
- فاکتورهای بدون شماره‌ی مالیاتی مؤدیان (`moadian_pending`، فقط خواندنی)
- ثبت نهایی (Submit) یک سند پیش‌نویس، با تأیید (`submit_document`، تغییر با تأیید)
