#!/usr/bin/env python3
"""Runs the morning council and delivers it to Telegram. Called by cron."""
import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def main():
    from brothers import load_all, _brothers
    from core import council
    load_all()

    # Warm the Intel Circle so the council has fresh signals to read
    for cmd, bid in [("ai news", "alpha"), ("hn", "hn"),
                     ("search world news today", "search"),
                     ("fear", "crypto"), ("price BTC", "crypto"),
                     ("weather", "weather")]:
        try:
            if bid in _brothers:
                _brothers[bid].run(cmd)
        except Exception as e:
            print(f"  [scheduled] {bid} warmup failed: {e}")

    # Convene
    report = council.convene(task="morning briefing")
    print(report)

    # Deliver to Telegram if configured
    token   = os.getenv("TELEGRAM_TOKEN", "")
    channel = os.getenv("TELEGRAM_CHANNEL", "")
    if token and channel:
        try:
            # Telegram caps messages at 4096 chars
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel, "text": report[:4000]},
                timeout=15)
            print("\n  [scheduled] delivered to Telegram")
        except Exception as e:
            print(f"\n  [scheduled] Telegram delivery failed: {e}")
    else:
        print("\n  [scheduled] no Telegram configured — printed only")

if __name__ == "__main__":
    main()
