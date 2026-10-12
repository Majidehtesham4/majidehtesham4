# ERPNext ایرانی (iran_erp)

بومی‌سازی ERPNext نسخه ۱۶ برای ایران، به‌صورت یک اپ جدا (`iran_erp`) که روی ERPNext نصب می‌شود
و به هسته‌ی ERPNext دست نمی‌زند؛ بنابراین ارتقای ERPNext ساده می‌ماند.

## امکانات فعلی

| امکان | توضیح |
|---|---|
| تاریخ شمسی | فیلدهای تاریخ در فرم‌ها و فیلترهای گزارش به شمسی نمایش داده می‌شوند و با تقویم شمسی یا تایپ (مثلاً `1405/08/01` یا `۱۴۰۵/۰۸/۰۱`) پر می‌شوند؛ در پایگاه داده همچنان میلادی ذخیره می‌شود. در «تنظیمات ایرانی» (`/desk/iran-erp-settings`) می‌توان به ورود میلادی برگشت. فیلدهای تاریخ‌وساعت فعلاً میلادی‌اند |
| سال مالی شمسی | ساخت سال مالی از ۱ فروردین تا آخر اسفند، با در نظر گرفتن سال کبیسه (`iran_erp.api.create_jalali_fiscal_year`) |
| کد ملی / شناسه ملی / کد اقتصادی | فیلدهای جدید در مشتری، تأمین‌کننده و شرکت، با بررسی رقم کنترل؛ اعداد فارسی خودکار به لاتین تبدیل می‌شوند |
| تاریخ شمسی در چاپ | تابع `format_jalali(doc.posting_date)` و `to_persian_digits` در قالب‌های چاپ (Jinja) |
| ترجمه‌ی کامل فارسی | حدود ۳۴۰۰ عبارت ترجمه‌نشده یا ناهمگون Frappe و ERPNext، همراه با انتخابگر تاریخ فارسی |
| ریال | نمایش مبالغ ریالی بدون اعشار و بدون بریده شدن رقم‌های اول در جدول‌های راست‌به‌چپ |
| دستیار هوشمند | چت فارسی داخل سیستم، متصل به مدل‌های OpenRouter: جستجو، گزارش، ساخت سند و صفحه وب پیش‌نویس، خروجی Excel |

تصاویر نصب آزمایشی در [`docs/screenshots`](docs/screenshots) و گزارش کمبودهای ERPNext برای ایران در
[`docs/gap-report.md`](docs/gap-report.md) است.

## نصب روی سرور (با Docker)

پیش‌نیاز: یک سرور لینوکس با حداقل ۴ گیگ رم و Docker.

```bash
git clone https://github.com/majidehtesham4/majidehtesham4.git
cd majidehtesham4/erpnext-iran

# ساخت ایمیج ERPNext + iran_erp
docker build -t iran-erp:latest .

# تنظیم رمزها
cd deploy
cp .env.example .env
nano .env        # ADMIN_PASSWORD و DB_ROOT_PASSWORD را عوض کنید

# اجرا
docker compose up -d
```

ساخت سایت اول بار چند دقیقه طول می‌کشد (`docker compose logs -f create-site`).
بعد از آن سیستم روی `http://IP-سرور:8080` در دسترس است. نام کاربری `Administrator` و رمز همان
`ADMIN_PASSWORD` است. در ویزارد اولیه زبان «فارسی»، کشور «Iran» و منطقه‌ی زمانی `Asia/Tehran` را انتخاب کنید.

ساخت سال مالی شمسی (مثلاً ۱۴۰۵) پس از ویزارد:

```bash
docker compose exec backend bench --site frontend execute \
  iran_erp.api.create_jalali_fiscal_year --kwargs '{"jalali_year": 1405, "company": "نام شرکت"}'
```

نمایش همه‌ی ماژول‌ها (حسابداری، فروش، CRM، وب‌سایت و ...) به‌صورت آیکون در صفحه‌ی اول، به‌جای دو پوشه‌ی
ERPNext و چارچوب:

```bash
docker compose exec backend bench --site frontend execute iran_erp.desktop.use_icon_grid
```

## دستیار هوشمند (OpenRouter)

1. یک کلید API از [openrouter.ai/keys](https://openrouter.ai/keys) بسازید و اعتبار حساب را شارژ کنید.
2. در ERPNext به آدرس `/desk/iran-ai-settings` بروید (یا در جستجو «تنظیمات دستیار هوشمند» را بنویسید).
3. کلید را وارد کنید، شناسه‌ی مدل را از [openrouter.ai/models](https://openrouter.ai/models) بگذارید
   (پیش‌فرض `anthropic/claude-opus-5.5`) و ذخیره کنید. دکمه‌ی «آزمایش اتصال» کلید و مدل را بررسی می‌کند.
4. صفحه را بازخوانی کنید؛ دکمه‌ی «دستیار هوشمند» پایین صفحه ظاهر می‌شود.

دستیار با دسترسی‌های همان کاربری کار می‌کند که سؤال می‌پرسد، فقط سند **پیش‌نویس** می‌سازد و هیچ سندی را
ثبت نهایی، لغو یا حذف نمی‌کند. ساخت یا تغییر رکوردهای تنظیمات سیستم (کاربران، نقش‌ها، سفارشی‌سازی‌ها) برایش
بسته است. همه‌ی سؤال‌ها و کارهای انجام‌شده در «درخواست دستیار هوشمند» (`/desk/iran-ai-request`) ثبت می‌شوند.

## به‌روزرسانی سرور بعد از تغییرات جدید

```bash
cd ~/majidehtesham4 && git pull
cd erpnext-iran && docker build -t iran-erp:latest .
cd deploy && docker compose up -d
docker compose exec backend bench --site frontend migrate
```

برای اتصال دامنه و HTTPS از راهنمای
[frappe_docker](https://github.com/frappe/frappe_docker/tree/main/docs) استفاده کنید.

## توسعه

کد اپ در `apps/iran_erp` است. برای اجرای تست‌ها داخل یک bench:

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app iran_erp
```

## لایسنس

اپ `iran_erp` با لایسنس MIT است. ERPNext با لایسنس GPL-3.0 و فریم‌ورک Frappe با لایسنس MIT منتشر شده‌اند.
فایل `deploy/docker-compose.yml` بر پایه‌ی `pwd.yml` پروژه‌ی frappe_docker (MIT) ساخته شده است.
