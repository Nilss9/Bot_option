#!/usr/bin/env python3
# broadcast_once.py
import os
import logging
import asyncio
from datetime import datetime
import yfinance as yf
import redis
from telegram import Bot
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
BROADCAST_CHAT = os.getenv("BROADCAST_CHAT_ID")
MAJOR_STOCKS = ["AAPL","MSFT","AMZN","GOOG","NVDA","TSLA","META","BRK-B","JPM","V"]
SUBSCRIBERS_KEY = "subscribers:set"

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN not set")
    raise SystemExit(1)

bot = Bot(token=TELEGRAM_TOKEN)

# try redis; if not available fallback to data/subscribers.json
redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        redis_client = None

DATA_FILE = "data/subscribers.json"

def fetch_price_line(sym):
    try:
        tk = yf.Ticker(sym)
        info = tk.info or {}
        price = info.get("regularMarketPrice")
        prev = info.get("previousClose")
        if price is None:
            return f"{sym}: بيانات غير متوفرة"
        ch = price - (prev or 0)
        pct = (ch / prev * 100) if prev else 0
        return f"{sym}: {price} ({ch:+.2f}, {pct:+.2f}%)"
    except Exception:
        return f"{sym}: خطأ"

async def main():
    lines = []
    for s in MAJOR_STOCKS:
        lines.append(fetch_price_line(s))
    text = "*تحديث أسواق (تلقائي)*\n" + "\n".join(lines)

    # try broadcast chat first
    if BROADCAST_CHAT:
        try:
            await bot.send_message(chat_id=BROADCAST_CHAT, text=text, parse_mode="Markdown")
            logger.info("Broadcast sent to BROADCAST_CHAT")
            return
        except Exception:
            logger.exception("Failed to send to BROADCAST_CHAT")

    # otherwise to subscribers
    subs = []
    if redis_client:
        try:
            subs = list(redis_client.smembers(SUBSCRIBERS_KEY))
        except Exception:
            logger.exception("Failed to read redis subscribers")
    else:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as fh:
                subs = json.load(fh)
        except Exception:
            subs = []

    if not subs:
        logger.info("No subscribers to send to.")
        return
    # batch send
    batch_size = 20
    for i in range(0, len(subs), batch_size):
        batch = subs[i:i+batch_size]
        tasks = []
        for chat in batch:
            try:
                tasks.append(bot.send_message(chat_id=int(chat), text=text, parse_mode="Markdown"))
            except Exception:
                logger.exception("Queue failed for %s", chat)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
