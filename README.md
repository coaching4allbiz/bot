# Coaching4all – راشد AI

بوت تليجرام احترافي للكوتشينغ اليومي باستخدام الذكاء الاصطناعي (DeepSeek V4).

## المميزات

- رحلة Onboarding كاملة (تعارف + جمع بيانات + تقييم شخصية)
- نظام اشتراكات (Free / Paid) مع حدود يومية
- حفظ المحادثات والبيانات في PostgreSQL أو SQLite
- نظام Streak يومي
- سياق المحادثات السابقة للـ AI
- أوامر أدمن
- Webhook آمن (المسار يحتوي على التوكن)

## التقنيات

- Python 3.10+
- Flask + Gunicorn
- pyTelegramBotAPI
- DeepSeek API (`deepseek-v4-flash` / `deepseek-v4-pro`)
- PostgreSQL (موصى به على Render) أو SQLite

## متغيرات البيئة المطلوبة

```
TELEGRAM_BOT_TOKEN=
DEEPSEEK_API_KEY=
ADMIN_TELEGRAM_ID=
DATABASE_URL=          # Internal URL من Render
WEBHOOK_URL=https://your-service.onrender.com
FREE_DAILY_LIMIT=35
PAID_DAILY_LIMIT=130
```

## إعدادات Render

- **Service Type**: Web Service
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn bot:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`

> ملاحظة: استخدم `--workers 1` لأن Rate Limiting حالياً في الذاكرة.

## الأوامر المتاحة للمستخدم

- `/start` – بدء أو العودة
- `/help` – قائمة الأوامر
- `/profile` – عرض الملف الشخصي
- `/streak` – السلسلة اليومية
- `/privacy` – سياسة الخصوصية
- `/delete_my_data` – حذف جميع البيانات

## أوامر الأدمن

- `/admin_stats`
- `/admin_user [telegram_id]`
- `/admin_recent`

## ملاحظات مهمة

1. بعد أي تحديث للكود، تأكد أن الـ Webhook ما زال مفعّلاً (يتم تعيينه تلقائياً عند تشغيل السيرفر).
2. التقييم الشخصي مبسّط وتفاعلي عبر الـ AI (ليس استبيانات ثابتة طويلة).
3. لحذف بيانات مستخدم: `/delete_my_data`

---
تم التطوير بواسطة Coaching4all | 2026
