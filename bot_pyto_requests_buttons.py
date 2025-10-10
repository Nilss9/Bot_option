#!/usr/bin/env python3
# bot_pyto_requests_buttons.py
"""
بوت تيليجرام (متوافق مع Pyto)
- يحتوي زر: 📈 قائمة أهم الأسهم
- يحتوي زر: 🕒 حالة السوق  -> يعرض إذا كانت جلسة السوق الأمريكية مفتوحة الآن (مع توقيت السعودية)
- يعمل بدون yfinance (يستخدم requests)
"""

import os, json, logging, asyncio, requests
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# ---------------- إعداد ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CFG_FILE = "config.json"
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
SUB_FILE = os.path.join(DATA_DIR, "subscribers.json")
if not os.path.exists(SUB_FILE):
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

def load_cfg():
    with open(CFG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

cfg = load_cfg()
TELEGRAM_TOKEN = cfg.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise SystemExit("⚠️ ضع TELEGRAM_TOKEN في config.json")

# ---------------- إدارة المشتركين ----------------
def get_subs():
    try:
        with open(SUB_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_subs(subs_set):
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(subs_set), f, ensure_ascii=False)

async def add_sub(chat_id):
    subs = get_subs()
    subs.add(str(chat_id))
    save_subs(subs)

async def rem_sub(chat_id):
    subs = get_subs()
    subs.discard(str(chat_id))
    save_subs(subs)

# ---------------- بيانات الأسهم ----------------
YAHOO_URL = "https://query1.finance.yahoo.com/v7/finance/quote"

def fetch_symbol(symbol):
    try:
        r = requests.get(YAHOO_URL, params={"symbols": symbol}, timeout=10)
        r.raise_for_status()
        data = r.json()["quoteResponse"]["result"]
        if not data: return None
        q = data[0]
        return {
            "symbol": q.get("symbol"),
            "price": q.get("regularMarketPrice"),
            "change": q.get("regularMarketChange"),
            "percent": q.get("regularMarketChangePercent")
        }
    except Exception as e:
        logger.error(e)
        return None

async def async_fetch(symbol):
    return await asyncio.to_thread(fetch_symbol, symbol)

# ---------------- واجهة الأزرار ----------------
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    ["📊 سعر سهم", "📅 تواريخ الأوبشن"],
    ["📈 قائمة أهم الأسهم", "🕒 حالة السوق"],
    ["🔔 تشغيل التحديثات", "⛔️ إيقاف التحديثات"],
    ["❓ مساعدة"]
], resize_keyboard=True)

TOP10 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "BRK-B", "JPM", "NFLX"]

# ---------------- حالة السوق (NY <-> Riyadh) ----------------
NY_TZ = ZoneInfo("America/New_York")
RIYADH_TZ = ZoneInfo("Asia/Riyadh")
MARKET_OPEN_NY = dtime(9, 30)
MARKET_CLOSE_NY = dtime(16, 0)

def is_market_open_now():
    """
    Returns tuple (is_open:bool, now_ny:datetime, open_dt_ny:datetime, close_dt_ny:datetime)
    Note: does not check market holidays.
    """
    now_ny = datetime.now(tz=NY_TZ)
    open_dt = datetime.combine(now_ny.date(), MARKET_OPEN_NY, tzinfo=NY_TZ)
    close_dt = datetime.combine(now_ny.date(), MARKET_CLOSE_NY, tzinfo=NY_TZ)
    # weekends
    if now_ny.weekday() >= 5:
        return (False, now_ny, open_dt, close_dt)
    return (open_dt <= now_ny <= close_dt, now_ny, open_dt, close_dt)

def format_market_status_msg():
    is_open, now_ny, open_dt, close_dt = is_market_open_now()
    # convert times to Riyadh
    now_riy = now_ny.astimezone(RIYADH_TZ)
    open_riy = open_dt.astimezone(RIYADH_TZ)
    close_riy = close_dt.astimezone(RIYADH_TZ)
    # human readable
    ny_fmt = lambda dt: dt.strftime("%Y-%m-%d %H:%M (%Z)")
    riy_fmt = lambda dt: dt.strftime("%Y-%m-%d %H:%M (%Z)")
    status = "مفتوحة ✅" if is_open else "مغلقة ⛔️"
    msg = (
        f"🕒 حالة السوق الأمريكي: *{status}*\n\n"
        f"*الآن (نيويورك):* {ny_fmt(now_ny)}\n"
        f"*الآن (الرياض):* {riy_fmt(now_riy)}\n\n"
        f"⏰ مواعيد الجلسة الاعتيادية (نيويورك):\n"
        f"فتح: {ny_fmt(open_dt)}\n"
        f"إغلاق: {ny_fmt(close_dt)}\n\n"
        f"⏰ نفسها بالتوقيت السعودي (الرياض):\n"
        f"فتح: {riy_fmt(open_riy)}\n"
        f"إغلاق: {riy_fmt(close_riy)}\n\n"
        f"_ملاحظة: لا يتم التحقق من العطلات الرسمية. إن أردت فأنفّذ التحقق._"
    )
    return msg

# ---------------- أوامر ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name or "صديقي"
    await update.message.reply_text(
        f"👋 أهلاً {user}!\n"
        "أنا بوت الأسهم الأمريكية.\n"
        "اختر من الأزرار أدناه 👇",
        reply_markup=MAIN_KEYBOARD
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧭 الأوامر:\n"
        "/price SYMBOL - سعر السهم\n"
        "/on /off - تشغيل أو إيقاف التنبيهات\n"
        "/help - المساعدة\n",
        reply_markup=MAIN_KEYBOARD
    )

async def on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_sub(update.effective_chat.id)
    await update.message.reply_text("✅ تم تشغيل التنبيهات.", reply_markup=MAIN_KEYBOARD)

async def off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rem_sub(update.effective_chat.id)
    await update.message.reply_text("⛔️ تم إيقاف التنبيهات.", reply_markup=MAIN_KEYBOARD)

async def show_top10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 جاري جلب الأسعار، انتظر لحظة...")
    texts = []
    for sym in TOP10:
        q = await async_fetch(sym)
        if q and q.get("price") is not None:
            texts.append(f"{q['symbol']}: {q['price']:.2f} ({q['percent']:+.2f}%)")
        else:
            texts.append(f"{sym}: -")
    msg = "📈 **أهم الأسهم الآن:**\n" + "\n".join(texts)
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def show_market_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = format_market_status_msg()
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

# ---------------- التعامل مع الأزرار ----------------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "📊 سعر سهم":
        await update.message.reply_text("🔎 أرسل رمز السهم مثل: AAPL أو TSLA")
    elif txt == "📅 تواريخ الأوبشن":
        await update.message.reply_text("📅 استخدم الأمر /expiries SYMBOL")
    elif txt == "📈 قائمة أهم الأسهم":
        await show_top10(update, context)
    elif txt == "🕒 حالة السوق":
        await show_market_status(update, context)
    elif txt == "🔔 تشغيل التحديثات":
        await on_cmd(update, context)
    elif txt == "⛔️ إيقاف التحديثات":
        await off_cmd(update, context)
    elif txt == "❓ مساعدة":
        await help_cmd(update, context)
    else:
        await update.message.reply_text("❓ لم أفهم اختيارك.", reply_markup=MAIN_KEYBOARD)

# ---------------- تشغيل ----------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("on", on_cmd))
    app.add_handler(CommandHandler("off", off_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    logger.info("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()