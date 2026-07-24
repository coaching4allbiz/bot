# Coaching4all – راشد AI

بوت تليجرام احترافي للكوتشينغ اليومي باستخدام الذكاء الاصطناعي (DeepSeek V4).

## التحديثات الأخيرة (يوليو 2026)

- جعل تقييم الشخصية **اختيارياً** مع تفضيل الاختبارات الخارجية الموثوقة
- إضافة شرح مبسط جداً للكوتشينغ + تأكيد فهم التوقعات قبل البدء
- تحسين رحلة الـ Onboarding وتقليل الاحتكاك
- تحديث سياسة الخصوصية

## المميزات

- رحلة Onboarding محسنة (تعارف + شرح الكوتشينغ + تأكيد الفهم)
- تقييم شخصية اختياري (يفضل المواقع الخارجية مثل 16Personalities)
- نظام اشتراكات (Free / Paid) مع حدود يومية
- حفظ المحادثات والبيانات في PostgreSQL أو SQLite
- نظام Streak يومي
- سياق المحادثات السابقة للـ AI
- أوامر أدمن
- Webhook آمن

## التقنيات

- Python 3.10+
- Flask + Gunicorn
- pyTelegramBotAPI
- DeepSeek API (`deepseek-v4-flash` / `deepseek-v4-pro`)
- PostgreSQL (موصى به) أو SQLite

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

---
تم التطوير بواسطة Coaching4all | 2026
