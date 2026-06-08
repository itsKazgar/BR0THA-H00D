"""
social_scout.py — BR0THER Social Intelligence Agent
Monitors CT, tech, politics, macro — writes to brain so trader stays tuned in.
"""
import requests, re, time, sys, os
from xml.etree import ElementTree as ET
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

INTERVAL = 180  # scan every 3 mins
NITTER_BASES = ["https://nitter.net", "https://nitter.privacydev.net"]
HEADERS = {"User-Agent": "Mozilla/5.0"}
CA_PATTERN     = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')
SYMBOL_PATTERN = re.compile(r'\$([A-Z]{2,10})\b')

WATCH_ACCOUNTS = {
    # === SOLANA CORE ===
    "aeyakovenko":    10,
    "rajgokal":       10,
    "solana":          8,
    "JupiterExchange": 7,
    "pumpdotfun":      6,

    # === TOP CRYPTO TRADERS / CT ALPHA ===
    "blknoiz06":       9,  # Ansem
    "DegenSpartan":    8,
    "cobie":           7,
    "inversebrah":     7,
    "CryptoKaleo":     7,
    "CryptoCobain":    7,
    "hsaka":           7,
    "gainzy222":       6,
    "notthreadguy":    6,
    "mando_crypto":    6,
    "hsakatrades":     7,
    "zhusu":           6,
    "kyled116":        6,
    "SmallCapScience": 7,
    "AltcoinSherpa":   6,
    "thedefiedge":     6,
    "lookonchain":     8,  # on-chain alpha
    "spotonchain":     7,
    "bubblemaps":      7,

    # === MEMECOIN / DEGEN ===
    "weremeow":        7,
    "solanalegend":    7,
    "hype_eth":        6,
    "iamDCinvestor":   6,
    "0xngmi":          6,
    "dingalingts":     6,
    "trader1sz":       7,

    # === CRYPTO MACRO / NEWS ===
    "cz_binance":      7,
    "saylor":          6,
    "VitalikButerin":  6,
    "brian_armstrong":  6,
    "EleanorTerrett":  6,  # crypto policy/news
    "WatcherGuru":     7,  # breaking news
    "WuBlockchain":    6,
    "BitcoinMagazine": 5,
    "CoinDesk":        5,
    "Cointelegraph":   5,

    # === TECH / AI (narratives move markets) ===
    "elonmusk":        9,  # moves markets
    "sama":            7,  # Sam Altman — AI narrative
    "karpathy":        6,
    "naval":           6,
    "paulg":           5,
    "balajis":         7,  # crypto+tech
    "pmarca":          6,

    # === POLITICS / MACRO (affects risk-on/off) ===
    "realDonaldTrump": 8,  # market mover
    "POTUS":           6,
    "federalreserve":  7,
    "SecYellen":       6,
}

ALPHA_KEYWORDS = [
    "just launched","new token","early","gem","100x","buying","accumulating",
    "loaded","CA:","contract:","pump","solana launch","just deployed",
    "stealth launch","fair launch","liquidity added","going to pump",
    "next 100x","undervalued","hidden gem","aping","aped in",
]

NARRATIVE_KEYWORDS = {
    "ai_meta":    ["ai agent","artificial intelligence","llm","gpt","claude","chatgpt","ai token","ai coin"],
    "meme_meta":  ["meme coin","memecoin","dog coin","cat coin","pepe","doge","shib"],
    "defi_meta":  ["defi","yield","liquidity","amm","dex","lending","borrow"],
    "btc_meta":   ["bitcoin","btc","sats","halving","etf","blackrock"],
    "reg_meta":   ["sec","regulation","congress","bill","law","ban","approved","rejected"],
    "fear_meta":  ["crash","rug","scam","hack","exploit","emergency","warning","danger"],
    "greed_meta": ["bull run","all time high","ath","parabolic","euphoria","moon","sending"],
}

seen = set()

def fetch(account):
    for base in NITTER_BASES:
        try:
            r = requests.get(f"{base}/{account}/rss", headers=HEADERS, timeout=8)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = []
                for item in root.findall(".//item"):
                    title = item.find("title").text or ""
                    desc  = item.find("description").text or ""
                    link  = item.find("link").text or ""
                    items.append({"account": account, "text": title+" "+desc, "title": title, "link": link, "id": link})
                return items
        except:
            continue
    return []

def analyze(tweet, weight):
    text = tweet["text"]
    tl   = text.lower()
    score = 0
    signals = []

    cas     = [c for c in CA_PATTERN.findall(text) if 32 <= len(c) <= 44]
    symbols = [s for s in SYMBOL_PATTERN.findall(text.upper()) if s not in {"THE","AND","FOR","SOL","USD","BTC","ETH","NFT","API","SDK","AI","VC"}]
    kws     = [k for k in ALPHA_KEYWORDS if k in tl]
    is_rt   = text.startswith("RT by")

    if cas:     score += 40 * weight; signals.append(f"CA:{cas[0][:8]}...")
    if symbols: score += 20 * weight; signals.append(f"${','.join(symbols[:2])}")
    if kws:     score += 15 * weight; signals.append(f"kw:{kws[0]}")
    if not is_rt: score += 10 * weight

    # detect narrative
    for meta, words in NARRATIVE_KEYWORDS.items():
        if any(w in tl for w in words):
            signals.append(meta)
            score += 5 * weight

    if score < 15: return None
    return {"account": tweet["account"], "weight": weight, "score": score,
            "signals": signals, "cas": cas, "symbols": symbols,
            "text": tweet["title"][:200], "link": tweet["link"], "is_rt": is_rt}

def run():
    print(f"  📡 SOCIAL SCOUT — watching {len(WATCH_ACCOUNTS)} accounts across CT/tech/politics")
    while True:
        all_signals = []
        new = 0
        for account, weight in WATCH_ACCOUNTS.items():
            tweets = fetch(account)
            for t in tweets:
                if t["id"] in seen: continue
                seen.add(t["id"]); new += 1
                s = analyze(t, weight)
                if s: all_signals.append(s)
            time.sleep(0.3)

        all_signals.sort(key=lambda x: x["score"], reverse=True)

        # Write top signals to brain
        for s in all_signals[:5]:
            sig_str = " | ".join(s["signals"])
            msg = f"@{s['account']} (w={s['weight']}) score={s['score']}: {sig_str} — {s['text'][:80]}"
            brain.learn("social_scout", "ct_signal", msg)
            if s["cas"]:
                brain.learn("social_scout", "ca_alert", f"CA from @{s['account']}: {s['cas'][0]} — {s['text'][:60]}")
            print(f"  📡 [{s['account']}] {sig_str}")

        # Write narrative summary
        narrative_counts = {}
        for s in all_signals:
            for sig in s["signals"]:
                if sig.endswith("_meta"):
                    narrative_counts[sig] = narrative_counts.get(sig, 0) + 1
        if narrative_counts:
            top = sorted(narrative_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            summary = ", ".join([f"{k}x{v}" for k,v in top])
            brain.learn("social_scout", "narrative", f"trending narratives: {summary}")
            print(f"  📡 narratives: {summary}")

        print(f"  📡 {new} new posts | {len(all_signals)} signals | next in {INTERVAL//60}min")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
