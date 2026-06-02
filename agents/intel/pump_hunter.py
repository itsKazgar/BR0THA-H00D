CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'; BD='\033[1m'; DM='\033[2m'; RS='\033[0m'
import requests, time, sys, os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

INTERVAL  = 10   # very fast — catch launches early
MIN_MCAP  = 8_000
MAX_MCAP  = 500_000
MIN_LIQ   = 8_000   # must be tradeable
MAX_AGE_H = 2    # only very fresh — under 2h

seen = set()

SOURCES = [
    "https://api.dexscreener.com/token-profiles/latest/v1",
    "https://api.dexscreener.com/token-boosts/latest/v1",
]

def get(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def fetch_pair(mint):
    data = get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    if not data:
        return None
    pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"]
    if not pairs:
        return None
    import time as t
    p = sorted(pairs, key=lambda x: float(x.get("liquidity",{}).get("usd",0) or 0), reverse=True)[0]
    age = (t.time() - (p.get("pairCreatedAt", 0) or 0) / 1000) / 3600
    return {
        "name":    p.get("baseToken", {}).get("symbol", "?"),
        "mint":    p.get("baseToken", {}).get("address", ""),
        "price":   float(p.get("priceUsd", 0) or 0),
        "mcap":    float(p.get("marketCap", 0) or 0),
        "liq":     float(p.get("liquidity", {}).get("usd", 0) or 0),
        "vol":     float(p.get("volume", {}).get("h24", 0) or 0),
        "buys":    int(p.get("txns", {}).get("h1", {}).get("buys", 0) or 0),
        "sells":   int(p.get("txns", {}).get("h1", {}).get("sells", 0) or 0),
        "change":  float(p.get("priceChange", {}).get("h1", 0) or 0),
        "age":     round(age, 1),
        "url":     p.get("url", ""),
    }

def gem_score(d):
    s = 0
    if d["buys"] > 50:   s += 20
    if d["buys"] > 20:   s += 10
    total = d["buys"] + d["sells"]
    if total > 0 and d["buys"]/total > 0.7: s += 20
    if d["liq"] > 20_000:  s += 20
    elif d["liq"] > 8_000: s += 10
    if 5 <= d["change"] <= 50:  s += 20
    if d["age"] < 1:  s += 15
    elif d["age"] < 3: s += 10
    if MIN_MCAP < d["mcap"] < 100_000: s += 15
    return min(s, 100)

def scan():
    now   = datetime.now().strftime("%H:%M:%S")
    gems  = []

    for url in SOURCES:
        data = get(url)
        if not data:
            continue
        items = data if isinstance(data, list) else []
        for item in items:
            if item.get("chainId") != "solana":
                continue
            mint = item.get("tokenAddress", "")
            if not mint or mint in seen:
                continue
            d = fetch_pair(mint)
            if not d:
                continue
            if d["mcap"] < MIN_MCAP or d["mcap"] > MAX_MCAP:
                continue
            if d["liq"] < MIN_LIQ:
                continue
            if d["age"] > MAX_AGE_H:
                continue
            score = gem_score(d)
            if score >= 40:
                gems.append({**d, "score": score})
            seen.add(mint)
        time.sleep(0.3)

    gems.sort(key=lambda x: x["score"], reverse=True)

    if not gems:
        print(f"  [{now}] 💊 no pump gems found")
        return

    print(f"\n{RD}{BD}╔══════════════════════════════════════╗{RS}")
    print(f"{RD}{BD}║  💊 PUMP HUNTER  {now}             ║{RS}")

    for g in gems[:5]:
        ratio = g["buys"] / max(1, g["buys"] + g["sells"])
        color = GR if g["score"] >= 70 else YL
        print(f"\n  {color}{BD}▶ {g['name']}{RS} {DM}({g['mint'][:8]}...){RS}")
        print(f"     age={g['age']}h  mcap=${g['mcap']:,.0f}  liq=${g['liq']:,.0f}")
        print(f"     buys={g['buys']}  sells={g['sells']}  ratio={ratio:.0%}  1h={g['change']:+.1f}%")
        print(f"     {color}gem score={g['score']}/100{RS}")
        print(f"     {DM}{g['url']}{RS}")

        brain.remember("pump_hunter",
            f"PUMP GEM {g['name']} | mint={g['mint']} | "
            f"age={g['age']}h | mcap=${g['mcap']:,.0f} | "
            f"liq=${g['liq']:,.0f} | score={g['score']}",
            type="pump_gem",
            tags=f"{g['name'].lower()},pump,gem")

        if g["score"] >= 70:
            brain.share_idea("pump_hunter",
                f"PUMP GEM: {g['name']} score={g['score']}/100 age={g['age']}h mcap=${g['mcap']:,.0f}")

    print(f"{RD}{BD}╚══════════════════════════════════════╝{RS}\n")

def run():
    brain.init_db()
    print(f"{RD}{BD}💊 PUMP HUNTER{RS} — finding early pump.fun gems")
    print(f"   Filters: mcap<${MAX_MCAP:,}  age<{MAX_AGE_H}h  liq>${MIN_LIQ:,}")
    print(f"   Interval: {INTERVAL}s  |  Press Ctrl+C to stop\n")
    scan()
    while True:
        try:
            time.sleep(INTERVAL)
            scan()
        except KeyboardInterrupt:
            print("\n[pump_hunter] stopped.")
            break
        except Exception as e:
            print(f"[pump_hunter] error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
