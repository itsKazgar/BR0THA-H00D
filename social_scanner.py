"""
social_scanner.py - BR0THA Social Intelligence
Uses free RSS feeds from crypto news sources.
No API keys, no accounts needed.
"""

import requests
import re
import time
from xml.etree import ElementTree as ET
from datetime import datetime

RSS_FEEDS = {
    "CoinDesk":      ("https://www.coindesk.com/arc/outboundfeeds/rss/", "news"),
    "Cointelegraph": ("https://cointelegraph.com/rss",                   "news"),
    "Decrypt":       ("https://decrypt.co/feed",                         "news"),
    "TheBlock":      ("https://www.theblock.co/rss.xml",                 "news"),
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

CA_PATTERN     = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')
SYMBOL_PATTERN = re.compile(r'\$([A-Z]{2,10})\b')
IGNORE_SYMBOLS = {"THE","AND","FOR","SOL","USD","BTC","ETH","NFT","API","SDK","AI","VC"}

ALPHA_KEYWORDS = [
    "launched","new token","early","gem","100x","buying","accumulating",
    "pump","deployed","stealth launch","fair launch","liquidity",
    "airdrop","exploit","hack","rug","scam","sec","regulation",
    "etf","approved","rejected","blackrock","halving",
]

NARRATIVE_KEYWORDS = {
    "ai_meta":    ["ai agent","artificial intelligence","llm","gpt","ai token"],
    "meme_meta":  ["meme coin","memecoin","pepe","doge","dog coin"],
    "defi_meta":  ["defi","yield","liquidity","amm","dex","lending"],
    "btc_meta":   ["bitcoin","btc","sats","halving","etf","blackrock"],
    "reg_meta":   ["sec","regulation","congress","bill","ban","approved","rejected"],
    "fear_meta":  ["crash","rug","scam","hack","exploit","warning","emergency"],
    "greed_meta": ["bull run","all time high","ath","parabolic","moon","rally"],
}

seen = set()


def fetch_feed(name, url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        items = []
        for item in root.findall(".//item"):
            title = item.find("title")
            desc  = item.find("description")
            link  = item.find("link")
            date  = item.find("pubDate")
            t = title.text if title is not None else ""
            d = desc.text  if desc  is not None else ""
            l = link.text  if link  is not None else ""
            dt = date.text if date  is not None else ""
            items.append({
                "source": name,
                "text":   t + " " + d,
                "title":  t,
                "link":   l,
                "date":   dt,
                "id":     l,
            })
        return items
    except Exception as e:
        print(f"  ⚠️  {name} feed error: {e}")
        return []


def analyze(item):
    text     = item["text"]
    text_low = text.lower()
    signals  = []
    score    = 0

    # Contract addresses
    cas = [c for c in CA_PATTERN.findall(text) if 32 <= len(c) <= 44]
    if cas:
        score += 50
        signals.append(f"CA:{cas[0][:8]}...")

    # Token symbols
    symbols = [s for s in SYMBOL_PATTERN.findall(text.upper()) if s not in IGNORE_SYMBOLS]
    if symbols:
        score += 15
        signals.append(f"{', '.join(['$'+s for s in symbols[:3]])}")

    # Alpha keywords
    kws = [k for k in ALPHA_KEYWORDS if k in text_low]
    if kws:
        score += 10 * min(len(kws), 3)
        signals.append(f"kw: {', '.join(kws[:3])}")

    # Narratives
    matched_narratives = []
    for meta, words in NARRATIVE_KEYWORDS.items():
        if any(w in text_low for w in words):
            matched_narratives.append(meta)
            score += 8
    if matched_narratives:
        signals.extend(matched_narratives)

    if score < 15:
        return None

    return {
        "source":     item["source"],
        "score":      score,
        "signals":    signals,
        "cas":        cas,
        "symbols":    symbols,
        "title":      item["title"][:200],
        "link":       item["link"],
        "date":       item["date"],
        "narratives": matched_narratives,
    }


def scan_social():
    all_signals = []
    new_items   = 0

    for name, (url, _) in RSS_FEEDS.items():
        items = fetch_feed(name, url)
        for item in items:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            new_items += 1
            s = analyze(item)
            if s:
                all_signals.append(s)
        time.sleep(0.3)

    all_signals.sort(key=lambda x: x["score"], reverse=True)
    return all_signals, new_items


def format_signal(s):
    print(f"\n{'='*55}")
    print(f"  [{s['source']}] score={s['score']}")
    print(f"  {s['title'][:180]}")
    print(f"  Signals: {' | '.join(s['signals'])}")
    if s["cas"]:
        print(f"  ⚡ CA: {s['cas'][0]}")
    if s["symbols"]:
        print(f"  🎯 {', '.join(['$'+x for x in s['symbols']])}")
    print(f"  {s['link']}")
    print(f"  {s['date']}")


if __name__ == "__main__":
    print("BR0THA SOCIAL SCANNER — free RSS mode\n")
    print(f"Watching {len(RSS_FEEDS)} feeds: {', '.join(RSS_FEEDS.keys())}")

    while True:
        print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')} UTC] Scanning feeds...")
        signals, new = scan_social()
        print(f"  {new} new items | {len(signals)} signals")

        # Narrative summary
        narrative_counts = {}
        for s in signals:
            for n in s["narratives"]:
                narrative_counts[n] = narrative_counts.get(n, 0) + 1
        if narrative_counts:
            top = sorted(narrative_counts.items(), key=lambda x: x[1], reverse=True)[:4]
            print(f"  📊 trending: {', '.join([f'{k}x{v}' for k,v in top])}")

        for s in signals[:5]:
            format_signal(s)

        if not signals:
            print("  Nothing significant detected.")

        print(f"\n  Next scan in 5 min...")
        time.sleep(300)
