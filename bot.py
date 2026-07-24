#!/usr/bin/env python3
"""
Coaching4all - راشد AI
Updated Version - Committee Recommendations Implemented
- Optional personality assessment (prefer external tests)
- Simple coaching explanation + expectation confirmation
- Improved onboarding + privacy consent
"""

import os
import logging
import time
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional
from flask import Flask, request
import telebot
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ==================== إعداد قاعدة البيانات ====================
DB_TYPE = "postgres" if os.getenv("DATABASE_URL") else "sqlite"

if DB_TYPE == "postgres":
    import psycopg2
    from psycopg2.extras import RealDictCursor
else:
    import sqlite3

# ==================== الإعدادات ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
BUSINESS_ACCOUNT = "@coaching4allbiz"
DATABASE_URL = os.getenv("DATABASE_URL")
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "35"))
PAID_DAILY_LIMIT = int(os.getenv("PAID_DAILY_LIMIT", "130"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="HTML", threaded=False)
app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== Rate Limiting ====================
user_message_times: Dict[int, list] = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 20

def is_rate_limited(telegram_id: int) -> bool:
    now = time.time()
    user_times = user_message_times[telegram_id]
    user_times[:] = [t for t in user_times if now - t < RATE_LIMIT_WINDOW]
    if len(user_times) >= RATE_LIMIT_MAX:
        return True
    user_times.append(now)
    return False

# ==================== دوال قاعدة البيانات ====================

def get_db_connection():
    if DB_TYPE == "postgres":
        return psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect("coaching4all.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """إنشاء الجداول + إضافة الأعمدة الناقصة تلقائياً (Migration)"""
    conn = get_db_connection()
    c = conn.cursor()

    if DB_TYPE == "postgres":
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                tier TEXT DEFAULT 'free',
                goals TEXT,
                preferred_name TEXT,
                date_of_birth TEXT,
                gender TEXT,
                city TEXT,
                occupation TEXT,
                marital_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                current_streak INTEGER DEFAULT 0,
                last_streak_date DATE,
                onboarding_completed BOOLEAN DEFAULT FALSE,
                current_onboarding_step TEXT DEFAULT 'start',
                big_five_result TEXT,
                hexaco_result TEXT,
                disc_result TEXT,
                openjung_result TEXT,
                coaching_understood BOOLEAN DEFAULT FALSE
            )
        ''')

        columns_to_add = [
            ("goals", "TEXT"),
            ("preferred_name", "TEXT"),
            ("date_of_birth", "TEXT"),
            ("gender", "TEXT"),
            ("city", "TEXT"),
            ("occupation", "TEXT"),
            ("marital_status", "TEXT"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("last_active", "TIMESTAMP"),
            ("current_streak", "INTEGER DEFAULT 0"),
            ("last_streak_date", "DATE"),
            ("onboarding_completed", "BOOLEAN DEFAULT FALSE"),
            ("current_onboarding_step", "TEXT DEFAULT 'start'"),
            ("big_five_result", "TEXT"),
            ("hexaco_result", "TEXT"),
            ("disc_result", "TEXT"),
            ("openjung_result", "TEXT"),
            ("coaching_understood", "BOOLEAN DEFAULT FALSE"),
        ]

        for col_name, col_type in columns_to_add:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception as e:
                logger.warning(f"Could not add column {col_name}: {e}")

        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                role TEXT,
                content TEXT,
                model_used TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_usage (
                telegram_id BIGINT,
                usage_date DATE,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (telegram_id, usage_date)
            )
        ''')
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                tier TEXT DEFAULT 'free',
                goals TEXT,
                preferred_name TEXT,
                date_of_birth TEXT,
                gender TEXT,
                city TEXT,
                occupation TEXT,
                marital_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                current_streak INTEGER DEFAULT 0,
                last_streak_date TEXT,
                onboarding_completed INTEGER DEFAULT 0,
                current_onboarding_step TEXT DEFAULT 'start',
                big_five_result TEXT,
                hexaco_result TEXT,
                disc_result TEXT,
                openjung_result TEXT,
                coaching_understood INTEGER DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                role TEXT,
                content TEXT,
                model_used TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_usage (
                telegram_id INTEGER,
                usage_date DATE,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (telegram_id, usage_date)
            )
        ''')

    conn.commit()
    conn.close()
    logger.info("Database initialized / migrated successfully")

def get_or_create_user(telegram_id: int, first_name: str = "", username: str = "") -> Dict[str, Any]:
    conn = get_db_connection()
    c = conn.cursor()

    if DB_TYPE == "postgres":
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = c.fetchone()
    else:
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()

    if user:
        if DB_TYPE == "postgres":
            c.execute("UPDATE users SET last_active = %s WHERE telegram_id = %s",
                      (datetime.utcnow(), telegram_id))
        else:
            c.execute("UPDATE users SET last_active = ? WHERE telegram_id = ?",
                      (datetime.utcnow().isoformat(), telegram_id))
        conn.commit()
        conn.close()
        return dict(user)
    else:
        if DB_TYPE == "postgres":
            c.execute('''
                INSERT INTO users (telegram_id, first_name, username, tier, onboarding_completed, current_onboarding_step, last_active)
                VALUES (%s, %s, %s, 'free', FALSE, 'start', %s)
            ''', (telegram_id, first_name, username, datetime.utcnow()))
        else:
            c.execute('''
                INSERT INTO users (telegram_id, first_name, username, tier, onboarding_completed, current_onboarding_step, last_active)
                VALUES (?, ?, ?, 'free', 0, 'start', ?)
            ''', (telegram_id, first_name, username, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "username": username,
            "tier": "free",
            "onboarding_completed": False if DB_TYPE == "postgres" else 0,
            "current_onboarding_step": "start",
            "current_streak": 0,
            "coaching_understood": False if DB_TYPE == "postgres" else 0
        }

def update_user_profile(telegram_id: int, field: str, value: str):
    allowed = ['goals', 'preferred_name', 'date_of_birth', 'gender', 'city',
               'occupation', 'marital_status', 'big_five_result', 'hexaco_result',
               'disc_result', 'openjung_result']
    if field not in allowed:
        return
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute(f"UPDATE users SET {field} = %s WHERE telegram_id = %s", (value, telegram_id))
    else:
        c.execute(f"UPDATE users SET {field} = ? WHERE telegram_id = ?", (value, telegram_id))
    conn.commit()
    conn.close()

def update_user_step(telegram_id: int, step: str):
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("UPDATE users SET current_onboarding_step = %s WHERE telegram_id = %s", (step, telegram_id))
    else:
        c.execute("UPDATE users SET current_onboarding_step = ? WHERE telegram_id = ?", (step, telegram_id))
    conn.commit()
    conn.close()

def update_onboarding_completed(telegram_id: int, completed: bool = True):
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("UPDATE users SET onboarding_completed = %s, current_onboarding_step = 'completed' WHERE telegram_id = %s",
                  (completed, telegram_id))
    else:
        c.execute("UPDATE users SET onboarding_completed = ?, current_onboarding_step = 'completed' WHERE telegram_id = ?",
                  (int(completed), telegram_id))
    conn.commit()
    conn.close()

def set_coaching_understood(telegram_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("UPDATE users SET coaching_understood = TRUE WHERE telegram_id = %s", (telegram_id,))
    else:
        c.execute("UPDATE users SET coaching_understood = 1 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def delete_user_data(telegram_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("DELETE FROM users WHERE telegram_id = %s", (telegram_id,))
        c.execute("DELETE FROM messages WHERE telegram_id = %s", (telegram_id,))
        c.execute("DELETE FROM daily_usage WHERE telegram_id = %s", (telegram_id,))
    else:
        c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        c.execute("DELETE FROM messages WHERE telegram_id = ?", (telegram_id,))
        c.execute("DELETE FROM daily_usage WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def log_message(telegram_id: int, role: str, content: str, model_used: str = None):
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('INSERT INTO messages (telegram_id, role, content, model_used) VALUES (%s, %s, %s, %s)',
                  (telegram_id, role, content, model_used))
    else:
        c.execute('INSERT INTO messages (telegram_id, role, content, model_used) VALUES (?, ?, ?, ?)',
                  (telegram_id, role, content, model_used))
    conn.commit()
    conn.close()

def get_recent_messages(telegram_id: int, limit: int = 8) -> List[Dict[str, str]]:
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('''
            SELECT role, content FROM messages
            WHERE telegram_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        ''', (telegram_id, limit))
        rows = c.fetchall()
    else:
        c.execute('''
            SELECT role, content FROM messages
            WHERE telegram_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (telegram_id, limit))
        rows = c.fetchall()
    conn.close()

    messages = []
    for row in reversed(rows):
        if DB_TYPE == "postgres":
            messages.append({"role": row[0], "content": row[1]})
        else:
            messages.append({"role": row["role"], "content": row["content"]})
    return messages

def get_daily_message_count(telegram_id: int) -> int:
    today = date.today().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('SELECT message_count FROM daily_usage WHERE telegram_id = %s AND usage_date = %s',
                  (telegram_id, today))
    else:
        c.execute('SELECT message_count FROM daily_usage WHERE telegram_id = ? AND usage_date = ?',
                  (telegram_id, today))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0] if DB_TYPE == "postgres" else result["message_count"]
    return 0

def increment_daily_count(telegram_id: int):
    today = date.today().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('''
            INSERT INTO daily_usage (telegram_id, usage_date, message_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (telegram_id, usage_date)
            DO UPDATE SET message_count = daily_usage.message_count + 1
        ''', (telegram_id, today))
    else:
        c.execute('''
            INSERT INTO daily_usage (telegram_id, usage_date, message_count)
            VALUES (?, ?, 1)
            ON CONFLICT(telegram_id, usage_date)
            DO UPDATE SET message_count = message_count + 1
        ''', (telegram_id, today))
    conn.commit()
    conn.close()

def check_daily_limit(telegram_id: int, tier: str) -> bool:
    count = get_daily_message_count(telegram_id)
    limit = PAID_DAILY_LIMIT if tier == "paid" else FREE_DAILY_LIMIT
    return count < limit

def update_streak(telegram_id: int):
    today = date.today()
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()

    conn = get_db_connection()
    c = conn.cursor()

    if DB_TYPE == "postgres":
        c.execute("SELECT last_streak_date, current_streak FROM users WHERE telegram_id = %s", (telegram_id,))
    else:
        c.execute("SELECT last_streak_date, current_streak FROM users WHERE telegram_id = ?", (telegram_id,))

    row = c.fetchone()
    if row:
        last_date = str(row[0]) if row[0] else None
        streak = row[1] or 0
        if last_date == today_str:
            pass
        elif last_date == yesterday_str:
            streak += 1
        else:
            streak = 1

        if DB_TYPE == "postgres":
            c.execute("UPDATE users SET current_streak = %s, last_streak_date = %s WHERE telegram_id = %s",
                      (streak, today, telegram_id))
        else:
            c.execute("UPDATE users SET current_streak = ?, last_streak_date = ? WHERE telegram_id = ?",
                      (streak, today_str, telegram_id))
        conn.commit()
    conn.close()

def get_user_stats() -> Dict[str, Any]:
    conn = get_db_connection()
    c = conn.cursor()

    if DB_TYPE == "postgres":
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM daily_usage WHERE usage_date = %s", (date.today(),))
        active_today = c.fetchone()[0]
        c.execute("SELECT AVG(current_streak) FROM users")
        avg_streak = c.fetchone()[0] or 0
    else:
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM daily_usage WHERE usage_date = ?", (date.today().isoformat(),))
        active_today = c.fetchone()[0]
        c.execute("SELECT AVG(current_streak) FROM users")
        avg_streak = c.fetchone()[0] or 0

    conn.close()
    return {
        "total_users": total_users,
        "active_today": active_today,
        "average_streak": round(float(avg_streak), 1)
    }

def get_recent_users(limit: int = 10) -> List[Dict]:
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT telegram_id, first_name, tier, current_streak FROM users ORDER BY created_at DESC LIMIT %s", (limit,))
        users = c.fetchall()
        result = [dict(u) for u in users]
    else:
        c.execute("SELECT telegram_id, first_name, tier, current_streak FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
        users = c.fetchall()
        result = [{"telegram_id": u["telegram_id"], "first_name": u["first_name"],
                   "tier": u["tier"], "current_streak": u["current_streak"]} for u in users]
    conn.close()
    return result

def get_user_details(telegram_id: int) -> Optional[Dict]:
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = c.fetchone()
        result = dict(user) if user else None
    else:
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()
        result = dict(user) if user else None
    conn.close()
    return result

def is_non_coaching_query(text: str) -> bool:
    text_lower = text.lower()
    keywords = ['اشتراك', 'دفع', 'خدمة العملاء', 'دعم', 'ترقية', 'فاتورة',
                'استرجاع', 'payment', 'subscription', 'upgrade', 'billing']
    return any(kw in text_lower for kw in keywords)

def is_coaching_benefits_query(text: str) -> bool:
    text_lower = text.lower().strip()
    keywords = [
        'فائدة الكوتشينغ', 'فوائد الكوتشينغ', 'مزايا الكوتشينغ', 'ميزة الكوتشينغ',
        'فائدة الكوتشنج', 'فوائد الكوتشنج', 'مزايا الكوتشنج',
        'ليش الكوتشينغ', 'لماذا الكوتشينغ', 'وش فايدة الكوتشينغ', 'وش فائدة الكوتشينغ',
        'ما هي فوائد', 'ماهي فوائد', 'ما هي مزايا', 'ماهي مزايا',
        'فائدة الكوتشينج', 'فوائد الكوتشينج', 'مزايا الكوتشينج',
        'benefit of coaching', 'benefits of coaching', 'why coaching',
        'advantage of coaching', 'advantages of coaching',
        'ليش أحتاج كوتش', 'لماذا أحتاج كوتش', 'وش يفيدني الكوتشينغ',
        'فائدة الكوتش', 'فوائد الكوتش', 'مزايا الكوتش'
    ]
    return any(kw in text_lower for kw in keywords)

COACHING_BENEFITS_RESPONSE = """الكوتشينغ ليس مجرد نصائح، بل عملية منظمة تساعدك تكتشف إجاباتك بنفسك وتتحرك نحو أهدافك بوضوح وثقة.

<b>أهم فوائده:</b>

1. <b>وضوح أكبر</b>
   يساعدك ترى وضعك الحالي والنتائج التي تريدها بوضوح أكبر، بدل التشتت.

2. <b>اتخاذ قرارات أفضل</b>
   من خلال أسئلة قوية، تكتشف الخيارات المتاحة وتختار ما يناسبك أنت.

3. <b>مسؤولية ذاتية</b>
   ينقلك من انتظار الحلول إلى أخذ زمام المبادرة.

4. <b>استدامة التغيير</b>
   يركز على بناء عادات ووعي دائم.

5. <b>دعم غير متحيز</b>
   الكوتش لا يحكم عليك ولا يفرض رأيه.

في Coaching4all (راشد AI) نلتزم بمعايير الاتحاد الدولي للكوتشينغ (ICF).

هل تريد أن نبدأ الآن في موضوع معين؟"""

# ==================== البرومبت ====================

SYSTEM_PROMPT = """أنت راشد AI، كوتش محترف في Coaching4all. تتبع معايير الاتحاد الدولي للكوتشينغ (ICF) بدقة.

قواعد أساسية:
- لا تعطِ نصائح مباشرة أبداً. استخدم أسئلة قوية وعميقة تساعد العميل يكتشف إجابات نفسه.
- كن ودوداً ومهذباً ومحترماً وواضحاً.
- شجع على الاستمرارية وبناء السلسلة اليومية (Streak).
- ذكّر المستخدم بحقه في حذف بياناته باستخدام /delete_my_data عند الحاجة.
- تحدث باللغة العربية الفصحى المبسطة والواضحة جداً.
- ركز على التمكين والوعي الذاتي وليس على الحلول الجاهزة.
- إذا سأل العميل عن الكوتشينغ، اشرحه بأبسط طريقة ممكنة."""

def build_user_context(user: dict) -> str:
    parts = []
    if user.get("preferred_name"):
        parts.append(f"الاسم المفضل: {user['preferred_name']}")
    if user.get("goals"):
        parts.append(f"الهدف الرئيسي: {user['goals']}")
    if user.get("city"):
        parts.append(f"المدينة: {user['city']}")
    if user.get("occupation"):
        parts.append(f"المهنة/النشاط: {user['occupation']}")
    if user.get("current_streak"):
        parts.append(f"السلسلة الحالية: {user['current_streak']} يوم")
    if user.get("big_five_result"):
        parts.append(f"نتيجة شخصية: {user['big_five_result']}")
    return " | ".join(parts) if parts else ""

def get_coach_response(user_message: str, user_context: dict, model: str,
                       recent_messages: List[Dict] = None, extra_system: str = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if extra_system:
        messages.append({"role": "system", "content": extra_system})

    context_str = build_user_context(user_context)
    if context_str:
        messages.append({"role": "system", "content": f"معلومات عن العميل: {context_str}"})

    if recent_messages:
        for msg in recent_messages:
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    try:
        response = deepseek_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1800
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"DeepSeek Error: {e}")
        return "عذرًا، حدث خطأ فني مؤقت. حاول مرة أخرى بعد قليل."

# ==================== شرح الكوتشينغ المبسط ====================
SIMPLE_COACHING_EXPLANATION = """
<b>ما هو الكوتشينغ باختصار شديد؟</b>

الكوتشينغ = شراكة بينك وبيني.

أنا لا أعطيك نصائح جاهزة ولا أقول لك «افعل كذا».
بل أساعدك <b>تكتشف إجاباتك بنفسك</b> من خلال أسئلة قوية وتأمل.

<b>ماذا تتوقع مني؟</b>
• أسألك أسئلة تساعدك تفكر بوضوح
• أستمع لك باهتمام بدون حكم
• أساعدك ترى خياراتك وتختار ما يناسبك أنت
• أدعمك تبني عادات وتقدم يومي

<b>ماذا لا أفعله؟</b>
• لا أعالج مشاكل نفسية أو طبية
• لا أعطي استشارات مالية أو قانونية
• لا أفرض عليك رأيي

هل هذا واضح بالنسبة لك؟
اكتب «نعم واضح» أو «فهمت» حتى نبدأ معاً.
"""

PERSONALITY_CHOICE_MESSAGE = """
ممتاز 👍

الآن لديك خيار بخصوص فهم شخصيتك (اختياري تماماً):

<b>الخيار 1 (موصى به - الأفضل):</b>
قم باختبار شخصية موثوق من أحد هذه المواقع ثم أخبرني بالنتيجة باختصار:
• 16Personalities (عربي): https://www.16personalities.com/ar
• Truity Big Five: https://www.truity.com/test/big-five-personality-test

<b>الخيار 2:</b>
أسئلة قصيرة هنا في المحادثة (5 دقائق تقريباً)

<b>الخيار 3:</b>
تخطي الآن والبدء مباشرة في الكوتشينغ

اكتب رقم الخيار (1 أو 2 أو 3) أو «تخطي».
"""

def handle_onboarding(message, user: dict):
    user_id = message.from_user.id
    text = message.text.strip()
    step = user.get("current_onboarding_step", "start")
    skip = text.lower() in ["تخطي", "skip", "تخطي الآن", "لاحقاً", "لاحقا", "3"]

    # ===== الخطوة 1: الاسم المفضل =====
    if step == "start" or step == "preferred_name":
        if step == "start":
            update_user_step(user_id, "preferred_name")
            bot.reply_to(message,
                "مرحباً بك 🌟\n\n"
                "ما الاسم الذي تحب أن أناديك به؟\n"
                "(يمكنك كتابة اسمك الأول أو أي لقب تفضله)")
            return

        if not skip and len(text) > 1:
            update_user_profile(user_id, "preferred_name", text)
            preferred = text
        else:
            preferred = user.get("first_name") or "صديقي"
            update_user_profile(user_id, "preferred_name", preferred)

        update_user_step(user_id, "goals")
        bot.reply_to(message,
            f"تشرفت يا {preferred} 😊\n\n"
            "ما الهدف أو المجال الذي تريد العمل عليه معي؟\n"
            "(مثال: الثقة بالنفس، التوازن، المهنة، العلاقات، تطوير الذات...)")
        return

    # ===== الخطوة 2: الهدف =====
    if step == "goals":
        if not skip and len(text) > 2:
            update_user_profile(user_id, "goals", text)
        update_user_step(user_id, "explain_coaching")
        bot.reply_to(message, SIMPLE_COACHING_EXPLANATION)
        return

    # ===== الخطوة 3: شرح الكوتشينغ + تأكيد الفهم (إلزامي) =====
    if step == "explain_coaching":
        understood_keywords = ["نعم", "واضح", "فهمت", "تمام", "أوكي", "ok", "yes", "مفهوم", "نعم واضح", "فهمت تمام"]
        if any(kw in text.lower() for kw in understood_keywords):
            set_coaching_understood(user_id)
            update_user_step(user_id, "personality_choice")
            bot.reply_to(message, PERSONALITY_CHOICE_MESSAGE)
        else:
            bot.reply_to(message,
                "حتى نبدأ بشكل صحيح، أحتاج أتأكد أنك فهمت دوري.\n\n"
                "أنا لست مستشاراً أعطيك حلول جاهزة، بل أساعدك تكتشف إجاباتك بنفسك.\n\n"
                "هل هذا واضح؟ اكتب «نعم واضح» أو «فهمت».")
        return

    # ===== الخطوة 4: اختيار تقييم الشخصية (اختياري) =====
    if step == "personality_choice":
        text_lower = text.lower().strip()

        if text_lower in ["1", "اختبار", "خارجي", "موقع", "16", "truity"] or "1" in text_lower:
            update_user_step(user_id, "waiting_external_result")
            bot.reply_to(message,
                "ممتاز اختيار 👍\n\n"
                "اذهب إلى أحد هذه الاختبارات:\n"
                "• https://www.16personalities.com/ar\n"
                "• https://www.truity.com/test/big-five-personality-test\n\n"
                "بعد ما تخلص، ارجع هنا واكتب لي نتيجتك باختصار (مثلاً: ENFP أو نتائج Big Five).\n"
                "أو اكتب «تخطي» إذا غيرت رأيك.")
            return

        if text_lower in ["2", "أسئلة", "هنا", "محادثة"]:
            update_user_step(user_id, "short_reflection")
            bot.reply_to(message,
                "حسناً، سأطرح عليك 4 أسئلة قصيرة فقط.\n\n"
                "السؤال 1:\n"
                "عندما تواجه تحدياً جديداً، هل تميل إلى التخطيط مسبقاً أم التجربة مباشرة؟")
            return

        # تخطي أو 3
        update_onboarding_completed(user_id, True)
        preferred = user.get("preferred_name") or user.get("first_name") or "صديقي"
        bot.reply_to(message,
            f"تمام يا {preferred} ✅\n\n"
            "أنت الآن جاهز للكوتشينغ.\n"
            "اطرح أي موضوع تريد العمل عليه، وسأكون معك خطوة بخطوة.\n\n"
            "يمكنك دائماً استخدام:\n"
            "/profile - ملفك\n"
            "/streak - سلسلتك\n"
            "/delete_my_data - حذف بياناتك")
        return

    # ===== انتظار نتيجة الاختبار الخارجي =====
    if step == "waiting_external_result":
        if skip:
            update_onboarding_completed(user_id, True)
            bot.reply_to(message, "تم التخطي ✅\nيمكنك البدء الآن في أي موضوع.")
            return

        # حفظ النتيجة كنص حر
        update_user_profile(user_id, "big_five_result", text[:400])
        update_onboarding_completed(user_id, True)
        bot.reply_to(message,
            "شكراً لك، تم حفظ النتيجة ✅\n\n"
            "الآن أنت جاهز.\n"
            "ما الموضوع الذي تريد أن نبدأ العمل عليه؟")
        return

    # ===== أسئلة قصيرة داخل المحادثة =====
    if step == "short_reflection":
        # نجمع الإجابات ببساطة ونكمل
        recent = get_recent_messages(user_id, limit=6)
        # نحفظ آخر إجابة
        update_user_profile(user_id, "big_five_result", f"تأمل قصير: {text[:300]}")
        update_onboarding_completed(user_id, True)
        bot.reply_to(message,
            "شكراً على مشاركة تفكيرك ✅\n\n"
            "هذا يعطيني فكرة أفضل عن أسلوبك.\n"
            "الآن يمكننا البدء.\n"
            "ما الذي تريد التركيز عليه اليوم؟")
        return

    bot.reply_to(message, "شكراً. لنكمل.")

@bot.message_handler(commands=['start'])
def handle_start(message):
    user = get_or_create_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    preferred = user.get("preferred_name") or user.get("first_name") or "صديقي"
    streak = user.get("current_streak", 0)
    completed = user.get("onboarding_completed")
    is_completed = bool(completed) if completed is not None else False

    if is_completed:
        text = f"""مرحباً بعودتك يا {preferred} 👋

أنا <b>راشد AI</b>، كوتشك الشخصي.

🔥 سلسلتك الحالية: <b>{streak} يوم</b>

كيف يمكنني مساعدتك اليوم؟
يمكنك استخدام /help لرؤية الأوامر."""
        bot.reply_to(message, text)
        update_streak(message.from_user.id)
    else:
        text = f"""مرحباً {preferred} 👋

أنا <b>راشد AI</b> من Coaching4all.

قبل أن نبدأ، سأأخذ دقيقتين فقط لأشرح لك كيف نعمل معاً وأتأكد أن التوقعات واضحة.

هل أنت مستعد؟ اكتب أي شيء أو «ابدأ».

(يمكنك حذف بياناتك في أي وقت بـ /delete_my_data)"""
        bot.reply_to(message, text)
        update_user_step(message.from_user.id, "preferred_name")
        update_streak(message.from_user.id)

@bot.message_handler(commands=['help'])
def handle_help(message):
    text = """📋 <b>أوامر راشد AI</b>

/start - بدء أو العودة
/profile - عرض ملفك الشخصي
/streak - معرفة سلسلتك اليومية
/privacy - سياسة الخصوصية
/delete_my_data - حذف جميع بياناتك نهائياً

<b>للأدمن فقط:</b>
/admin_stats
/admin_user [id]
/admin_recent"""
    bot.reply_to(message, text)

@bot.message_handler(commands=['profile'])
def handle_profile(message):
    user = get_or_create_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    preferred = user.get("preferred_name") or user.get("first_name") or "—"
    text = f"""👤 <b>ملفك الشخصي</b>

• الاسم المفضل: {preferred}
• المستوى: {user.get('tier', 'free')}
• الهدف: {user.get('goals') or 'غير محدد'}
• السلسلة: {user.get('current_streak', 0)} يوم
• فهم الكوتشينغ: {'نعم' if user.get('coaching_understood') else '—'}
• ملاحظات شخصية: {user.get('big_five_result') or 'لم تُضف بعد'}

يمكنك تحديث بياناتك بالتحدث معي بشكل طبيعي."""
    bot.reply_to(message, text)

@bot.message_handler(commands=['streak'])
def handle_streak(message):
    user = get_or_create_user(message.from_user.id)
    streak = user.get("current_streak", 0)
    bot.reply_to(message, f"🔥 سلسلتك الحالية: <b>{streak} يوم</b>\n\nاستمر! كل يوم يبني قوة أكبر.")

@bot.message_handler(commands=['delete_my_data'])
def handle_delete_data(message):
    delete_user_data(message.from_user.id)
    bot.reply_to(message, "✅ تم حذف جميع بياناتك بنجاح.\nيمكنك البدء من جديد في أي وقت بـ /start")

@bot.message_handler(commands=['privacy'])
def handle_privacy(message):
    bot.reply_to(message,
        "<b>سياسة الخصوصية المحدثة</b>\n\n"
        "• نحن نحترم خصوصيتك بالكامل.\n"
        "• بياناتك تُستخدم فقط لتحسين تجربة الكوتشينغ معك.\n"
        "• يمكنك حذف جميع بياناتك في أي وقت باستخدام /delete_my_data\n"
        "• لا نشارك بياناتك مع أي طرف ثالث.\n\n"
        f"للاستفسارات: {BUSINESS_ACCOUNT}")

@bot.message_handler(commands=['admin_stats'])
def handle_admin_stats(message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    stats = get_user_stats()
    text = f"""📊 <b>إحصائيات Coaching4all</b>
• إجمالي المستخدمين: {stats['total_users']}
• نشطون اليوم: {stats['active_today']}
• متوسط السلسلة: {stats['average_streak']} يوم"""
    bot.reply_to(message, text)

@bot.message_handler(commands=['admin_user'])
def handle_admin_user(message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "استخدم: /admin_user [telegram_id]")
            return
        target_id = int(parts[1])
        user = get_user_details(target_id)
        if user:
            text = f"""👤 <b>بيانات المستخدم</b>
• الاسم: {user.get('first_name')}
• المفضل: {user.get('preferred_name')}
• المستوى: {user.get('tier')}
• الهدف: {user.get('goals', 'غير محدد')}
• السلسلة: {user.get('current_streak', 0)} يوم
• فهم الكوتشينغ: {user.get('coaching_understood')}
• onboarding: {user.get('onboarding_completed')}"""
            bot.reply_to(message, text)
        else:
            bot.reply_to(message, "لم يتم العثور على المستخدم.")
    except Exception as e:
        bot.reply_to(message, f"خطأ: {str(e)}")

@bot.message_handler(commands=['admin_recent'])
def handle_admin_recent(message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    users = get_recent_users(10)
    text = "<b>آخر 10 مستخدمين:</b>\n\n"
    for u in users:
        text += f"• {u.get('first_name')} | {u.get('tier')} | سلسلة: {u.get('current_streak', 0)}\n"
    bot.reply_to(message, text)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if not text:
        return

    if is_rate_limited(user_id):
        bot.reply_to(message, "ترسل رسائل بسرعة كبيرة. انتظر قليلاً من فضلك.")
        return

    user = get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)

    if not check_daily_limit(user_id, user.get("tier", "free")):
        bot.reply_to(message, f"وصلت للحد اليومي ({FREE_DAILY_LIMIT if user.get('tier') == 'free' else PAID_DAILY_LIMIT} رسالة).\nيمكنك الترقية عبر {BUSINESS_ACCOUNT}")
        return

    if is_non_coaching_query(text):
        bot.reply_to(message, f"للاستفسارات المتعلقة بالاشتراكات والدعم الفني: {BUSINESS_ACCOUNT}")
        return

    if is_coaching_benefits_query(text):
        bot.reply_to(message, COACHING_BENEFITS_RESPONSE)
        log_message(user_id, "user", text)
        log_message(user_id, "assistant", COACHING_BENEFITS_RESPONSE, "direct")
        increment_daily_count(user_id)
        update_streak(user_id)
        return

    completed = user.get("onboarding_completed")
    is_completed = bool(completed) if completed is not None else False

    if not is_completed:
        handle_onboarding(message, user)
        return

    # الوضع العادي (كوتشينغ حر)
    bot.send_chat_action(message.chat.id, 'typing')
    model = "deepseek-v4-pro" if user.get("tier") == "paid" else "deepseek-v4-flash"
    recent = get_recent_messages(user_id, limit=8)
    reply = get_coach_response(text, user, model, recent_messages=recent)

    bot.reply_to(message, reply)
    log_message(user_id, "user", text)
    log_message(user_id, "assistant", reply, model)
    increment_daily_count(user_id)
    update_streak(user_id)

@app.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/')
def index():
    return "Coaching4all Bot (راشد AI) is running with Webhooks!", 200

def setup_webhook():
    if WEBHOOK_URL and TELEGRAM_BOT_TOKEN:
        try:
            bot.remove_webhook()
            time.sleep(0.5)
            full_url = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_BOT_TOKEN}"
            bot.set_webhook(url=full_url)
            print(f"✅ Webhook set successfully to: {full_url}")
        except Exception as e:
            print(f"❌ Error setting webhook: {e}")
    else:
        print("⚠️ WEBHOOK_URL or TELEGRAM_BOT_TOKEN not set")

setup_webhook()
init_db()
