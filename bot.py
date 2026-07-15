#!/usr/bin/env python3
"""
Coaching4all - Final Reviewed Version
"""
import os
import logging
import time
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional
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

deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="HTML")

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
        return sqlite3.connect("coaching4all.db")

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    if DB_TYPE == "postgres":
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                first_name TEXT, username TEXT, tier TEXT DEFAULT 'free',
                goals TEXT, preferred_name TEXT, date_of_birth TEXT, gender TEXT,
                city TEXT, occupation TEXT, marital_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP, current_streak INTEGER DEFAULT 0,
                last_streak_date DATE,
                onboarding_completed BOOLEAN DEFAULT FALSE,
                current_onboarding_step TEXT DEFAULT 'start',
                big_five_result TEXT,
                hexaco_result TEXT,
                disc_result TEXT,
                openjung_result TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT, role TEXT, content TEXT, model_used TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_usage (
                telegram_id BIGINT, usage_date DATE, message_count INTEGER DEFAULT 0,
                PRIMARY KEY (telegram_id, usage_date)
            )
        ''')
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT, username TEXT, tier TEXT DEFAULT 'free',
                goals TEXT, preferred_name TEXT, date_of_birth TEXT, gender TEXT,
                city TEXT, occupation TEXT, marital_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP, current_streak INTEGER DEFAULT 0,
                last_streak_date TEXT,
                onboarding_completed INTEGER DEFAULT 0,
                current_onboarding_step TEXT DEFAULT 'start',
                big_five_result TEXT,
                hexaco_result TEXT,
                disc_result TEXT,
                openjung_result TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER, role TEXT, content TEXT, model_used TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_usage (
                telegram_id INTEGER, usage_date DATE, message_count INTEGER DEFAULT 0,
                PRIMARY KEY (telegram_id, usage_date)
            )
        ''')

    conn.commit()
    conn.close()

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
        conn.close()
        if DB_TYPE == "postgres":
            return dict(user)
        else:
            keys = ["telegram_id", "first_name", "username", "tier", "goals", "preferred_name",
                    "date_of_birth", "gender", "city", "occupation", "marital_status",
                    "created_at", "last_active", "current_streak", "last_streak_date",
                    "onboarding_completed", "current_onboarding_step",
                    "big_five_result", "hexaco_result", "disc_result", "openjung_result"]
            return dict(zip(keys, user))
    else:
        if DB_TYPE == "postgres":
            c.execute('''
                INSERT INTO users (telegram_id, first_name, username, tier, onboarding_completed, current_onboarding_step)
                VALUES (%s, %s, %s, 'free', FALSE, 'start')
            ''', (telegram_id, first_name, username))
        else:
            c.execute('''
                INSERT INTO users (telegram_id, first_name, username, tier, onboarding_completed, current_onboarding_step)
                VALUES (?, ?, ?, 'free', 0, 'start')
            ''', (telegram_id, first_name, username))
        conn.commit()
        conn.close()
        return {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "username": username,
            "tier": "free",
            "onboarding_completed": False,
            "current_onboarding_step": "start"
        }

def update_user_profile(telegram_id: int, field: str, value: str):
    conn = get_db_connection()
    c = conn.cursor()
    allowed = ['goals', 'preferred_name', 'date_of_birth', 'gender', 'city', 'occupation', 'marital_status']
    if field in allowed:
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
        c.execute("UPDATE users SET onboarding_completed = %s WHERE telegram_id = %s", (completed, telegram_id))
    else:
        c.execute("UPDATE users SET onboarding_completed = ? WHERE telegram_id = ?", (int(completed), telegram_id))
    conn.commit()
    conn.close()

def update_personality_result(telegram_id: int, test_name: str, result: str):
    conn = get_db_connection()
    c = conn.cursor()
    column = f"{test_name}_result"
    if DB_TYPE == "postgres":
        c.execute(f"UPDATE users SET {column} = %s WHERE telegram_id = %s", (result, telegram_id))
    else:
        c.execute(f"UPDATE users SET {column} = ? WHERE telegram_id = ?", (result, telegram_id))
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
        c.execute("DELETE FROM daily_usage WHERE telegram_id = ?", (telegram_id))
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

def get_daily_message_count(telegram_id: int) -> int:
    today = date.today().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('SELECT message_count FROM daily_usage WHERE telegram_id = %s AND usage_date = %s', (telegram_id, today))
    else:
        c.execute('SELECT message_count FROM daily_usage WHERE telegram_id = ? AND usage_date = ?', (telegram_id, today))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

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

# ==================== دوال مساعدة للأدمن ====================

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
        "average_streak": round(avg_streak, 1)
    }

def get_recent_users(limit: int = 10) -> List[Dict]:
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT telegram_id, first_name, tier, current_streak FROM users ORDER BY created_at DESC LIMIT %s", (limit,))
    else:
        c.execute("SELECT telegram_id, first_name, tier, current_streak FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
    users = c.fetchall()
    conn.close()
    return [dict(u) if DB_TYPE == "postgres" else {"telegram_id": u[0], "first_name": u[1], "tier": u[2], "current_streak": u[3]} for u in users]

def get_user_details(telegram_id: int) -> Optional[Dict]:
    conn = get_db_connection()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = c.fetchone()
        if user:
            return dict(user)
    else:
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()
        if user:
            keys = ["telegram_id", "first_name", "username", "tier", "goals", "preferred_name",
                    "date_of_birth", "gender", "city", "occupation", "marital_status",
                    "current_streak", "onboarding_completed", "current_onboarding_step",
                    "big_five_result", "hexaco_result", "disc_result", "openjung_result"]
            return dict(zip(keys, user))
    conn.close()
    return None

# ==================== كشف الأسئلة غير الكوتشينغ ====================

def is_non_coaching_query(text: str) -> bool:
    text_lower = text.lower()
    keywords = ['اشتراك', 'دفع', 'خدمة العملاء', 'دعم', 'ترقية', 'فاتورة', 'استرجاع', 'payment', 'subscription']
    return any(kw in text_lower for kw in keywords)

# ==================== البرومبت ====================

SYSTEM_PROMPT = """أنت كوتش AI محترف في Coaching4all. تتبع معايير ICF.
- لا تعطِ نصائح مباشرة. استخدم أسئلة قوية.
- شجع على بناء الثقة من خلال السلسلة اليومية.
- ذكّر المستخدم بحقه في حذف بياناته باستخدام /delete_my_data."""

def get_coach_response(user_message: str, user_context: dict, model: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context_parts = []
    if user_context.get("preferred_name"):
        context_parts.append(f"الاسم المفضل: {user_context['preferred_name']}")
    if user_context.get("goals"):
        context_parts.append(f"الهدف: {user_context['goals']}")
    if user_context.get("current_streak"):
        context_parts.append(f"السلسلة: {user_context['current_streak']} يوم")
    if context_parts:
        messages.append({"role": "system", "content": " | ".join(context_parts)})
    messages.append({"role": "user", "content": user_message})

    try:
        response = deepseek_client.chat.completions.create(
            model=model, messages=messages, temperature=0.7, max_tokens=1500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"DeepSeek Error: {e}")
        return "عذرًا، حدث خطأ فني مؤقت."

def get_coach_response_with_dynamic_prompt(user_message: str, user_context: dict, model: str, dynamic_prompt: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": dynamic_prompt}
    ]
    
    context_parts = []
    if user_context.get("preferred_name"):
        context_parts.append(f"الاسم المفضل: {user_context['preferred_name']}")
    if user_context.get("goals"):
        context_parts.append(f"الهدف: {user_context['goals']}")
    if user_context.get("current_streak"):
        context_parts.append(f"السلسلة: {user_context['current_streak']} يوم")

    if context_parts:
        messages.append({"role": "system", "content": " | ".join(context_parts)})

    messages.append({"role": "user", "content": user_message})

    try:
        response = deepseek_client.chat.completions.create(
            model=model, messages=messages, temperature=0.7, max_tokens=1500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"DeepSeek Error: {e}")
        return "عذرًا، حدث خطأ فني مؤقت."

# ==================== معالجات البوت ====================

@bot.message_handler(commands=['start'])
def handle_start(message):
    user = get_or_create_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    streak = user.get("current_streak", 0)
    preferred = user.get("preferred_name") or user.get("first_name", "صديقي")

    text = f"""مرحبًا {preferred} 👋

أنا **راشد AI**، كوتشك الشخصي.

دوري أن أساعدك تفهم نفسك أكثر وتوصل لخيارات أوضح في حياتك.

🔥 سلسلتك الحالية: {streak} يوم

يمكنك حذف بياناتك في أي وقت باستخدام الأمر: /delete_my_data"""

    bot.reply_to(message, text)
    update_streak(message.from_user.id)

@bot.message_handler(commands=['delete_my_data'])
def handle_delete_data(message):
    delete_user_data(message.from_user.id)
    bot.reply_to(message, "✅ تم حذف جميع بياناتك بنجاح.")

@bot.message_handler(commands=['privacy'])
def handle_privacy(message):
    bot.reply_to(message, f"سياسة الخصوصية. للاستفسارات: {BUSINESS_ACCOUNT}")

# ==================== أوامر الأدمن ====================

@bot.message_handler(commands=['admin_stats'])
def handle_admin_stats(message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    stats = get_user_stats()
    text = f"""
📊 <b>إحصائيات Coaching4all</b>
• إجمالي المستخدمين: {stats['total_users']}
• نشطون اليوم: {stats['active_today']}
• متوسط السلسلة: {stats['average_streak']} يوم
"""
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
            text = f"""
👤 <b>بيانات المستخدم</b>
• الاسم: {user.get('first_name')}
• المستوى: {user.get('tier')}
• الهدف: {user.get('goals', 'غير محدد')}
• السلسلة: {user.get('current_streak', 0)} يوم
"""
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

@bot.message_handler(commands=['admin_streaks'])
def handle_admin_streaks(message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    bot.reply_to(message, "هذه الميزة قيد التطوير.")

# ==================== المعالج الرئيسي ====================

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if is_rate_limited(user_id):
        bot.reply_to(message, "ترسل رسائل بسرعة كبيرة. انتظر قليلاً.")
        return

    user = get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)
    step = user.get("current_onboarding_step", "start")

    if is_non_coaching_query(text):
        bot.reply_to(message, f"للاستفسارات المتعلقة بالاشتراكات والدعم: {BUSINESS_ACCOUNT}")
        return

    if not check_daily_limit(user_id, user["tier"]):
        bot.reply_to(message, "وصلت للحد اليومي.")
        return

    if step == "awaiting_coaching_experience":
        update_user_step(user_id, "collecting_basic_info")
        bot.send_chat_action(message.chat.id, 'typing')

        dynamic_prompt = """أنت الآن في مرحلة التعرف على العميل (المحادثة الثانية).

قواعد مهمة يجب اتباعها:
- تحدث بأسلوب ودي وطبيعي، كأنك تتحدث مع صديق.
- اسأل سؤالاً واحداً أو اثنين كحد أقصى في كل رد. لا تُثقل العميل بأسئلة كثيرة.
- ابدأ بجمع معلومات أساسية بلطف: مجال عمله أو نشاطه اليومي، ثم مدينته، ثم تاريخ ميلاده (يمكنه كتابة السنة فقط).
- استخدم عبارات مثل: "لو ما تمانع"، "هل تمانع"، "هل يناسبك".
- ربط المعلومات بالقيمة: أخبره بلطف أن هذه المعلومات تساعدك تفهمه بشكل أفضل.
- لا تطلب أي معلومات حساسة (مثل مشاكل صحية دقيقة، بيانات مالية، أو تفاصيل شخصية جداً).
- بعد جمع بعض المعلومات، يمكنك أن تسأله بلطف إن كان لديه أي تحديات أو أمور تشغل باله حالياً."""

        reply = get_coach_response_with_dynamic_prompt(text, user, "deepseek-v4-flash", dynamic_prompt)
        bot.reply_to(message, reply)
        log_message(user_id, "user", text)
        log_message(user_id, "assistant", reply, "deepseek-v4-flash")
        increment_daily_count(user_id)
        return

    bot.send_chat_action(message.chat.id, 'typing')
    model = "deepseek-v4-pro" if user["tier"] == "paid" else "deepseek-v4-flash"
    reply = get_coach_response(text, user, model)
    bot.reply_to(message, reply)
    log_message(user_id, "user", text)
    log_message(user_id, "assistant", reply, model)
    increment_daily_count(user_id)
    update_streak(user_id)

if __name__ == "__main__":
    print("🚀 Coaching4all Bot starting...")
    init_db()
    
    # هذا السطر مهم لحل مشكلة الـ 409
    bot.delete_webhook()
    
    bot.infinity_polling(skip_pending=True)
