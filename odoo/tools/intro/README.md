# اینتروی VERON ERP

دو اینتروی لوگو، ساخته‌شده با مرورگر (Chromium) و ffmpeg. لوگو خط‌به‌خط بازسازی شده تا هر خط جدا روشن و متحرک شود.

| صحنه | زمان | شرح |
|---|---|---|
| `signal` | ۸ ثانیه | نقطه‌ی نور و پینگ، کمان‌های سیگنال یکی‌یکی، کشیده شدن خطوط V و دایره‌ها، موج نور، نوشته با نوار نور قرمز |
| `metal` | ۹ ثانیه | نزدیک شدن آهسته‌ی دوربین، نور قرمز از پشت لوگو، روشن شدن خطوط مثل لامپ نئون، بازتاب سفید روی فلز، مه قرمز |

## ساختن

```bash
cd odoo/tools/intro
node render_video.js signal signal_v.mp4 60          # تصویر
python3 audio_intro.py signal signal.wav              # صدا (ساخته‌شده از موج سینوسی و نویز، بدون حق نشر کسی)
ffmpeg -i signal_v.mp4 -i signal.wav -c:v copy -c:a aac -b:a 256k -shortest veron-intro-signal.mp4
node stills.js metal 2.4 4.8 8.0                       # چند فریم برای بررسی
```

- نیاز: Node با Playwright (Chromium)، Python 3 با numpy، ffmpeg.
- زمان‌بندی، رنگ‌ها و اندازه‌ها در `intro.html` است (`signal()` و `metal()`).
- قلم Montserrat با مجوز SIL Open Font License است (`fonts/`).
