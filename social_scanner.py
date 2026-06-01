"""
social_scanner.py - BR0THA Social Intelligence

Monitors key CT accounts via Nitter RSS.
Detects CA mentions, token symbols, and alpha signals.
When a big account mentions a token -> instant priority scan.
"""

import requests
import re
import time
from xml.etree import ElementTree as ET
from datetime import datetime

# Accounts ranked by alpha weight — higher = more important signal
WATCH_ACCOUNTS = {
    "aeyakovenko":  10,  # Toly — Solana founder, mentions = massive
    "rajgokal":     10,  # Raj — Solana co-founder
    "solana":        8,  # Official Solana account
    "JupiterExchange": 7, # Jupiter — sees all swap flow
    "blknoiz06":     9,  # Ansem — one of best Solana traders
    "DegenSpartan":  8,  # Degen Spartan — respected CT trader
    "cobie":         7,  # Cobie — respected macro + crypto
    "inversebrah":   7,  # inversebrah — solid Solana alpha
    "pumpdotfun":    6,  # Pump.fun official
}

NITTER_BASE = "https://nitter.net"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Solana CA pattern — base58, 32-44 chars
CA_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# Token symbol pattern — $SYMBOL
SYMBOL_PATTERN = re.compile(r'\$([A-Z]{2,10})\b')

# Keywords that signal alpha
ALPHA_KEYWORDS = [
    "just launched", "new token", "early", "gem", "100x",
    "buying", "accumulating", "loaded", "CA:", "contract:",
    "pump", "solana launch", "just deployed", "stealth launch",
    "airdrop", "fair launch", "liquidity added"
]

seen_tweets = set()  # avoid processing same tweet twice


def fetch_feed(account):
    """Fetch RSS feed for an account."""
    try:
        r = requests.get(
            f"{NITTER_BASE}/{account}/rss",
            headers=HEADERS,
            timeout=10
        )
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        items = []
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            desc  = item.find("description").text or ""
            date  = item.find("pubDate").text or ""
            link  = item.find("link").text or ""
            full_text = title + " " + desc
            items.append({
                "account": account,
                "text":    full_text,
                "title":   title,
                "date":    date,
                "link":    link,
                "id":      link  # use link as unique ID
            })
        return items
    except Exception as e:
        return []


def analyze_tweet(tweet, weight):
    """
    Analyze a tweet for alpha signals.
    Returns a signal dict or None.
    """
    text = tweet["text"]
    text_upper = text.upper()
    signals = []
    score = 0

    # Check for Solana CA addresses
    cas = CA_PATTERN.findall(text)
    # Filter out common non-CA base58 strings (tx hashes are longer)
    cas = [ca for ca in cas if 32 <= len(ca) <= 44]
    if cas:
        score += 40 * weight
        signals.append(f"CA mentioned: {cas[0]}")

    # Check for token symbols
    symbols = SYMBOL_PATTERN.findall(text_upper)
    # Filter noise
    ignore = {"THE","AND","FOR","SOL","USD","BTC","ETH","NFT","API","SDK"}
    symbols = [s for s in symbols if s not in ignore]
    if symbols:
        score += 20 * weight
        signals.append(f"Token symbols: {', '.join(['$'+s for s in symbols[:3]])}")

    # Check alpha keywords
    text_lower = text.lower()
    found_keywords = [kw for kw in ALPHA_KEYWORDS if kw in text_lower]
    if found_keywords:
        score += 15 * weight
        signals.append(f"Keywords: {', '.join(found_keywords[:3])}")

    # Boost if it's an original tweet not a RT
    is_rt = text.startswith("RT by")
    if not is_rt:
        score += 10 * weight
        signals.append("Original tweet (not RT)")

    if score < 20:
        return None

    return {
        "account":  tweet["account"],
        "weight":   weight,
        "score":    score,
        "signals":  signals,
        "cas":      cas,
        "symbols":  symbols,
        "text":     tweet["title"][:200],
        "link":     tweet["link"],
        "date":     tweet["date"],
        "is_rt":    is_rt
    }


def scan_social():
    """
    Scan all watched accounts for alpha signals.
    Returns list of signals sorted by score.
    """
    all_signals = []
    new_tweets  = 0

    for account, weight in WATCH_ACCOUNTS.items():
        tweets = fetch_feed(account)
        for tweet in tweets:
            tid = tweet["id"]
            if tid in seen_tweets:
                continue
            seen_tweets.add(tid)
            new_tweets += 1

            signal = analyze_tweet(tweet, weight)
            if signal:
                all_signals.append(signal)

        time.sleep(0.5)  # be nice to nitter

    all_signals.sort(key=lambda x: x["score"], reverse=True)
    return all_signals, new_tweets


def format_signal(s):
    rt_tag = "[RT]" if s["is_rt"] else "[OG]"
    print(f"\n{'='*55}")
    print(f"  @{s['account']} {rt_tag} | score={s['score']} | weight={s['weight']}")
    print(f"  {s['text'][:180]}")
    print(f"  Signals: {' | '.join(s['signals'])}")
    if s["cas"]:
        print(f"  ⚡ CA FOUND: {s['cas'][0]}")
    if s["symbols"]:
        print(f"  🎯 Symbols: {', '.join(['$'+x for x in s['symbols']])}")
    print(f"  Link: {s['link']}")


if __name__ == "__main__":
    print("BR0THA SOCIAL SCANNER — monitoring CT alpha\n")
    print(f"Watching {len(WATCH_ACCOUNTS)} accounts...")

    while True:
        print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')} UTC] Scanning social feeds...")
        signals, new = scan_social()
        print(f"  {new} new tweets | {len(signals)} signals found")

        for s in signals[:5]:
            format_signal(s)

        if not signals:
            print("  No alpha detected this cycle.")

        print(f"\n[SLEEP] Next social scan in 2 min...")
        time.sleep(120)
