# ERPNext ایرانی (iran_erp)

بومی‌سازی ERPNext نسخه ۱۶ برای ایران، به‌صورت یک اپ جدا (`iran_erp`) که روی ERPNext نصب می‌شود
و به هسته‌ی ERPNext دست نمی‌زند؛ بنابراین ارتقای ERPNext ساده می‌ماند.

## امکانات فعلی (نسخه 0.0.1)

| امکان | توضیح |
|---|---|
| نمایش تاریخ شمسی | در لیست‌ها، گزارش‌ها و فیلدهای فقط‌خواندنی تاریخ به شمسی نمایش داده می‌شود؛ زیر فیلدهای تاریخِ قابل ویرایش هم معادل شمسی نوشته می‌شود |
| سال مالی شمسی | ساخت سال مالی از ۱ فروردین تا آخر اسفند، با در نظر گرفتن سال کبیسه (`iran_erp.api.create_jalali_fiscal_year`) |
| کد ملی / شناسه ملی / کد اقتصادی | فیلدهای جدید در مشتری، تأمین‌کننده و شرکت، با بررسی رقم کنترل؛ اعداد فارسی خودکار به لاتین تبدیل می‌شوند |
| تاریخ شمسی در چاپ | تابع `format_jalali(doc.posting_date)` و `to_persian_digits` در قالب‌های چاپ (Jinja) |
| ترجمه | فایل ترجمه‌ی فارسی برای پیام‌های این اپ |

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
