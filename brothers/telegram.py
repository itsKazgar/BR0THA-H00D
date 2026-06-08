import os, sys, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Telegram Brother"
DESCRIPTION = "Send messages and trade alerts to your Telegram"
ENABLED     = True
COMMANDS    = ["telegram <message>", "tg <message>", "telegram setup"]

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

def send(message: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=8)
        return r.status_code == 200
    except:
        return False

def run(user_input):
    lower = user_input.lower().strip()

    if lower == "telegram setup":
        return """📱 TELEGRAM SETUP (2 mins):

1. Open Telegram → search @BotFather
2. Send: /newbot
3. Follow steps → copy the token it gives you
4. Search @userinfobot → send /start → copy your chat ID
5. Add to your .env file:
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
6. Restart the assistant

That's it — trader will ping you on every buy/sell."""

    if lower.startswith("telegram ") or lower.startswith("tg "):
        if not BOT_TOKEN or not CHAT_ID:
            return "❌ Telegram not configured. Type: telegram setup"
        msg = user_input.split(" ", 1)[1].strip()
        ok  = send(msg)
        return f"✅ Sent to Telegram: {msg}" if ok else "❌ Telegram send failed — check token/chat_id in .env"

    if lower in ["telegram test", "tg test", "test telegram"]:
        if not BOT_TOKEN or not CHAT_ID:
            return "❌ Not configured. Type: telegram setup"
        ok = send("🤖 BR0THER test message — Telegram is working!")
        return "✅ Test sent! Check your Telegram." if ok else "❌ Failed — check .env"

    return None
