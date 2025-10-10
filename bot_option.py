#!/usr/bin/env python3
"""
bot_option.py
Telegram bot to query US stock price and options chain using yfinance.

Commands:
 /start           - ترحيب
 /help            - تعليمات
 /price SYMBOL    - إحضار سعر السهم الحالي (مثال: /price AAPL)
 /expiries SYMBOL - عرض التواريخ المتاحة للأوبشن
 /chain SYMBOL YYYY-MM-DD - عرض سلسلة الأوبشن لتاريخ انتهاء محدد (مثال: /chain AAPL 2025-10-17)
 /option SYMBOL YYYY-MM-DD TYPE STRIKE - استعلام عن خيار محدد (مثال: /option AAPL 2025-10-17 CALL 170)
"""

import os
import logging
from datetime import datetime
import yfinance as yf
from telegram import Update, ForceReply
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # ضع توكن البوت هنا كمتغير بيئة

if not TELEGRAM_TOKEN:
    logger.error("Please set TELEGRAM_TOKEN environment variable.")
    raise SystemExit("TELEGRAM_TOKEN not found in environment variables.")

# --- Helper functions ---
def safe_str(x):
    return str(x) if x is not None else "-"

def format_price_info(ticker):
    info = []
    try:
        price = ticker.info.get("regularMarketPrice")
        prev_close = ticker.info.get("previousClose")
        change = None
        if price is not None and prev_close is not None:
            try:
                change = price - prev_close
                pct = (change / prev_close) * 100 if prev_close != 0 else None
            except Exception:
                pct = None
        else:
            pct = None
        info.append(f"السهم: {safe_str(ticker.info.get('symbol'))}")
        info.append(f"السعر الحالي: {safe_str(price)}")
        info.append(f"إغلاق سابق: {safe_str(prev_close)}")
        if change is not None and pct is not None:
            info.append(f"التغير: {change:.2f} ({pct:.2f}%)")
        info.append(f"سعر أعلى اليوم: {safe_str(ticker.info.get('dayHigh'))}")
        info.append(f"سعر أدنى اليوم: {safe_str(ticker.info.get('dayLow'))}")
        info.append(f"حجم التداول اليومي: {safe_str(ticker.info.get('volume'))}")
    except Exception as e:
        logger.exception("Error formatting price info: %s", e)
        info.append("حدث خطأ أثناء جلب بيانات السهم.")
    return "\n".join(info)

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحبًا! أنا بوت للاستعلام عن أسهم السوق الأمريكي والأوبشن.\n"
        "استخدم /help لمشاهدة الأوامر المتاحة."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/price SYMBOL\n"
        "/expiries SYMBOL\n"
        "/chain SYMBOL YYYY-MM-DD\n"
        "/option SYMBOL YYYY-MM-DD TYPE STRIKE\n\n"
        "أمثلة:\n"
        "/price AAPL\n"
        "/expiries AAPL\n"
        "/chain AAPL 2025-10-17\n"
        "/option AAPL 2025-10-17 CALL 170"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("المرجوا تمرير رمز السهم. مثال: /price AAPL")
        return
    symbol = context.args[0].upper()
    await update.message.reply_text(f"جاري جلب سعر {symbol} ...")
    try:
        tk = yf.Ticker(symbol)
        text = format_price_info(tk)
    except Exception as e:
        logger.exception("Error fetching price for %s: %s", symbol, e)
        text = "حدث خطأ أثناء جلب بيانات السهم."
    await update.message.reply_text(text)

async def expiries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("استخدم: /expiries SYMBOL  (مثال: /expiries AAPL)")
        return
    symbol = context.args[0].upper()
    try:
        tk = yf.Ticker(symbol)
        exps = tk.options  # list of expiry strings like '2025-10-17'
        if not exps:
            await update.message.reply_text("لا توجد تواريخ انتهاء متاحة أو السهم غير صحيح.")
            return
        # show first 10 to keep it readable
        to_show = "\n".join(exps[:50])
        await update.message.reply_text(f"تواريخ انتهاء الأوبشن المتاحة لـ {symbol}:\n{to_show}")
    except Exception as e:
        logger.exception("Error fetching expiries for %s: %s", symbol, e)
        await update.message.reply_text("حدث خطأ أثناء جلب تواريخ الانتهاء.")

async def chain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استخدم: /chain SYMBOL YYYY-MM-DD")
        return
    symbol = context.args[0].upper()
    exp = context.args[1]
    try:
        tk = yf.Ticker(symbol)
        if exp not in tk.options:
            await update.message.reply_text("تاريخ الانتهاء غير موجود. استخدم /expiries للتحقق.")
            return
        opt = tk.option_chain(exp)
        calls = opt.calls
        puts = opt.puts
        # show top 10 calls and puts sorted by volume or openInterest
        def tabulate(df, kind):
            if df is None or df.empty:
                return f"لا توجد {kind}."
            df_sorted = df.sort_values(by=["openInterest"], ascending=False).head(10)
            lines = [f"{kind} (أعلى 10 حسب OpenInterest):"]
            for _, row in df_sorted.iterrows():
                lines.append(
                    f"Strike {row['strike']}: Bid {row['bid']} Ask {row['ask']} Last {row['lastPrice']} OI {int(row['openInterest'])} Vol {int(row['volume'])}"
                )
            return "\n".join(lines)
        text = f"سلسلة الأوبشن لـ {symbol} - Expiry: {exp}\n\n"
        text += tabulate(calls, "CALLS") + "\n\n" + tabulate(puts, "PUTS")
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("Error fetching chain for %s %s: %s", symbol, exp, e)
        await update.message.reply_text("حدث خطأ أثناء جلب سلسلة الأوبشن.")

async def option_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /option SYMBOL YYYY-MM-DD TYPE STRIKE
    if len(context.args) < 4:
        await update.message.reply_text("استخدم: /option SYMBOL YYYY-MM-DD TYPE STRIKE\nمثال: /option AAPL 2025-10-17 CALL 170")
        return
    symbol = context.args[0].upper()
    exp = context.args[1]
    kind = context.args[2].upper()  # CALL or PUT
    strike_str = context.args[3]
    try:
        strike = float(strike_str)
    except Exception:
        await update.message.reply_text("قيمة السترايك غير صحيحة. يجب أن تكون رقمًا، مثال 170 أو 170.0")
        return
    try:
        tk = yf.Ticker(symbol)
        if exp not in tk.options:
            await update.message.reply_text("تاريخ الانتهاء غير موجود. استخدم /expiries للتحقق.")
            return
        opt = tk.option_chain(exp)
        df = opt.calls if kind.startswith("C") else opt.puts
        # find exact strike (may not exactly match; choose closest)
        row = df.loc[df["strike"] == strike]
        if row.empty:
            # try nearest
            row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
            note = "(أقرب سترايك موجود)"
        else:
            note = ""
        r = row.iloc[0]
        text = (
            f"{symbol} {kind} Strike {r['strike']} Exp {exp}\n"
            f"Bid: {r['bid']}\nAsk: {r['ask']}\nLast Price: {r['lastPrice']}\n"
            f"Change: {r['change']}\nOpen Interest: {int(r['openInterest'])}\nVolume: {int(r['volume'])}\n{note}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("Error fetching option for %s %s %s %s: %s", symbol, exp, kind, strike, e)
        await update.message.reply_text("حدث خطأ أثناء جلب معلومات الخيار.")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("الأمر غير معروف. استخدم /help للاطلاع على الأوامر.")

# --- Main ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("expiries", expiries))
    app.add_handler(CommandHandler("chain", chain))
    app.add_handler(CommandHandler("option", option_single))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()