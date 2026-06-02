# colors
CY='[96m'; GR='[92m'; YL='[93m'; RD='[91m'; BD='[1m'; DM='[2m'; RS='[0m'
import requests, time, sys, os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

# ━━ FREE PUBLIC DATA SOURCES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEXSCREENER_TRENDING = "https://api.dexscreener.com/token-boosts/top/v1"
DEXSCREENER_LATEST   = "https://api.dexscreener.com/token-boosts/latest/v1"
DEXSCREENER_TOKEN    = "https://api.dexscreener.com/latest/dex/tokens/{}"
DEXSCREENER_SEARCH   = "https://api.dexscreener.com/latest/dex/search?q={}"
# pump.fun coins via DexScreener token profiles (frontend-api.pump.fun is blocked)
PUMP_FUN_PROFILES    = "https://api.dexscreener.com/token-profiles/latest/v1"
PUMP_FUN_NEW         = "https://api.dexscreener.com/latest/dex/search?q=pump"
PUMP_FUN_TRENDING    = "https://api.dexscreener.com/latest/dex/search?q=pumpfun"
# Direct new pairs — catches coins before they trend
DEXSCREENER_NEW_SOL  = "https://api.dexscreener.com/latest/dex/search?q=solana"
DEXSCREENER_RAYDIUM  = "https://api.dexscreener.com/latest/dex/pairs/solana/raydium"
DEXSCREENER_NEW_PAIRS = "https://api.dexscreener.com/token-profiles/latest/v1"
BIRDEYE_TRENDING     = "https://public-api.birdeye.so/defi/trending_tokens?chain=solana&limit=20"
DEFINED_TRENDING     = "https://api.defined.fi/graphql"
COINGECKO_TRENDING   = "https://api.coingecko.com/api/v3/search/trending"
SOLSCAN_TRANSFERS    = "https://pro-api.solscan.io/v2.0/token/transfer"

# ━━ KNOWN SMART WALLETS TO TRACK ━━━━━━━━━━━━━━━━━━━━━━━━
# Add more as you discover them
SMART_WALLETS = [
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # known SOL whale
    "5tzFkiKscXHK5ZXCGbCtEDFATCCrNPCa9x4rMcTFp5oF",  # degen alpha wallet
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",  # pump.fun sniper
]

SCAN_INTERVAL = 45   # seconds

# ━━ FILTERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MIN_LIQ       = 25_000
MIN_VOL_24H   = 50_000
MIN_TXNS_1H   = 50
MAX_CHANGE_1H = 200   # already pumped if >40% in 1h — too late to scalp 20%
MIN_CHANGE_1H = -15

seen = set()

# ━━ FETCHERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def fetch_dex_token(mint):
    data = get(DEXSCREENER_TOKEN.format(mint))
    if not data:
        return None
    pairs = data.get("pairs", [])
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol_pairs:
        return None
    p = sorted(sol_pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
    return parse_pair(p)

def parse_pair(p):
    try:
        return {
            "name":       p.get("baseToken", {}).get("symbol", "?"),
            "mint":       p.get("baseToken", {}).get("address", ""),
            "price":      float(p.get("priceUsd", 0) or 0),
            "volume_24h": float(p.get("volume", {}).get("h24", 0) or 0),
            "volume_1h":  float(p.get("volume", {}).get("h1", 0) or 0),
            "change_1h":  float(p.get("priceChange", {}).get("h1", 0) or 0),
            "change_24h": float(p.get("priceChange", {}).get("h24", 0) or 0),
            "change_5m":  float(p.get("priceChange", {}).get("m5", 0) or 0),
            "liquidity":  float(p.get("liquidity", {}).get("usd", 0) or 0),
            "mcap":       float(p.get("marketCap", 0) or 0),
            "buys_1h":    int(p.get("txns", {}).get("h1", {}).get("buys", 0) or 0),
            "sells_1h":   int(p.get("txns", {}).get("h1", {}).get("sells", 0) or 0),
            "age_hrs":    _age_hours(p.get("pairCreatedAt", 0)),
            "dex":        p.get("dexId", "?"),
            "url":        p.get("url", ""),
        }
    except:
        return None

def _age_hours(ts):
    try:
        if not ts: return 9999
        return round((time.time() - ts / 1000) / 3600, 1)
    except:
        return 9999

def fetch_dex_trending():
    coins = []
    for url in [DEXSCREENER_TRENDING, DEXSCREENER_LATEST]:
        data = get(url)
        if not data:
            continue
        items = data if isinstance(data, list) else data.get("pairs", [])
        for item in items[:30]:
            mint = item.get("tokenAddress", "")
            chain = item.get("chainId", "")
            if chain != "solana" or not mint:
                continue
            coins.append(mint)
    return list(set(coins))

def fetch_pump_coins(url):
    """Fetch early gems — handles DexScreener pairs format."""
    data = get(url)
    if not data:
        return []
    out = []
    pairs = data.get("pairs", []) if isinstance(data, dict) else []
    for p in pairs:
        if p.get("chainId") != "solana":
            continue
        mcap = float(p.get("marketCap", 0) or 0)
        vol  = float(p.get("volume", {}).get("h24", 0) or 0)
        liq  = float(p.get("liquidity", {}).get("usd", 0) or 0)
        age  = _age_hours(p.get("pairCreatedAt", 0))
        if mcap < 5_000 or age > 24 or liq < 1_000:
            continue
        out.append({
            "name":  p.get("baseToken", {}).get("symbol", "?"),
            "mint":  p.get("baseToken", {}).get("address", ""),
            "mcap":  mcap,
            "vol":   vol,
            "desc":  "",
        })
    return out[:20]

def fetch_pump_profiles():
    """Freshest pump.fun launches via DexScreener token profiles."""
    data = get(PUMP_FUN_PROFILES)
    if not data:
        return []
    mints = []
    for x in data:
        if x.get("chainId") != "solana":
            continue
        mint = x.get("tokenAddress", "")
        if mint:
            mints.append(mint)
    return mints[:30]

def fetch_coingecko_trending():
    data = get(COINGECKO_TRENDING)
    if not data:
        return []
    mints = []
    coins = data.get("coins", [])
    for c in coins:
        item = c.get("item", {})
        platforms = item.get("platforms", {})
        sol_mint = platforms.get("solana", "")
        if sol_mint:
            mints.append(sol_mint)
    return mints

def fetch_smart_wallet_activity():
    """Check smart wallet buys via DexScreener — look for tokens they hold."""
    found = []
    for wallet in SMART_WALLETS:
        try:
            # Use Solana FM public API (no key needed)
            url = f"https://api.solana.fm/v0/accounts/{wallet}/tokens"
            data = get(url)
            if not data:
                # Fallback: check recent transactions via DexScreener search
                continue
            tokens = data.get("result", []) or []
            for t in tokens[:10]:
                mint = t.get("mint", "") or t.get("tokenAddress", "")
                amount = float(t.get("amount", 0) or 0)
                if mint and amount > 0:
                    found.append({"wallet": wallet[:8]+"...", "mint": mint, "amount": amount})
        except:
            continue
    return found[:15]

def fetch_new_pairs():
    """Fetch brand new Solana pairs from DexScreener — best source for early gems."""
    found = []
    # Search for recently created Solana pairs
    for query in ["solana new", "sol pump", "raydium"]:
        data = get(DEXSCREENER_SEARCH.format(query))
        if not data:
            continue
        pairs = data.get("pairs", []) if isinstance(data, dict) else []
        for p in pairs:
            if p.get("chainId") != "solana":
                continue
            age = _age_hours(p.get("pairCreatedAt", 0))
            if age > 6:  # only pairs under 6 hours old
                continue
            mint = p.get("baseToken", {}).get("address", "")
            if mint:
                found.append(mint)
        time.sleep(0.2)
    return list(set(found))

# ━━ SCORING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def is_garbage_pump(d):
    """Looser filters for fresh pump.fun coins — they are tiny by nature."""
    if not d:                          return "no data"
    if d["liquidity"] < 8_000:        return f"liq ${d['liquidity']:,.0f} too low"
    if d["volume_24h"] < 8_000:       return f"vol ${d['volume_24h']:,.0f} too low"
    if d["buys_1h"] < 100:            return f"only {d['buys_1h']} buys — not enough interest"
    if d["change_1h"] > 800:          return "already nuked >800% — too late"
    if d["change_1h"] < -30:          return "dumping hard"
    if d["age_hrs"] > 6:              return f"too old for pump ({d['age_hrs']:.1f}h)"
    # vol/mcap ratio — must have real money flowing
    if d["mcap"] > 0 and d["volume_24h"] / d["mcap"] < 0.5:
        return "low vol/mcap — not enough interest"
    return None

def is_garbage(d):
    if not d:                              return "no data"
    if d["liquidity"] < MIN_LIQ:          return f"liq ${d['liquidity']:,.0f} too low"
    if d["volume_24h"] < MIN_VOL_24H:     return f"vol ${d['volume_24h']:,.0f} too low"
    if d["buys_1h"] < MIN_TXNS_1H:        return "not enough buys"
    if d["change_1h"] > 200:               return "already pumped >35%"
    if d["change_1h"] < MIN_CHANGE_1H:    return "dumping"
    if d["age_hrs"] < 0.5:  return "too fresh — under 30mins"
    if d["age_hrs"] > 48:                 return f"too old {d['age_hrs']:.0f}h"
    return None

def score_coin(d, sources=[]):
    s = 0
    r = []

    # ── Volume ───────────────────────────────────
    if d["volume_24h"] > 2_000_000:   s += 15; r.append("🔥 massive volume")
    elif d["volume_24h"] > 500_000:   s += 10; r.append("high volume")
    elif d["volume_24h"] > 100_000:   s +=  6; r.append("decent volume")
    elif d["volume_24h"] > 30_000:    s +=  3; r.append("low volume")

    # ── Volume acceleration (1h vs 24h avg) ──────
    # If 1h vol is more than 2x the hourly average, it's accelerating
    avg_1h = d["volume_24h"] / 24
    if avg_1h > 0:
        accel = d["volume_1h"] / avg_1h
        if accel > 5:    s += 12; r.append(f"⚡ vol x{accel:.0f} spike")
        elif accel > 3:  s +=  8; r.append(f"vol x{accel:.0f} accel")
        elif accel > 1.5:s +=  4; r.append(f"vol x{accel:.1f} rising")

    # ── 5m momentum — most actionable signal ─────
    c5 = d["change_5m"]
    if 3 <= c5 <= 20:    s += 20; r.append(f"🟢 {c5:+.1f}% 5m surge")
    elif 1 <= c5 < 3:    s += 10; r.append(f"📈 {c5:+.1f}% 5m up")
    elif c5 < -5:        s -= 15; r.append(f"🔴 {c5:+.1f}% 5m dump")

    # ── 1h momentum ───────────────────────────────
    c = d["change_1h"]
    if 5 <= c <= 25:     s += 20; r.append(f"🚀 {c:+.1f}% 1h sweet spot")
    elif 2 <= c < 5:     s += 12; r.append(f"📈 {c:+.1f}% building")
    elif 25 < c <= 40:   s -=  5; r.append(f"⚠️ {c:+.1f}% late entry")
    elif 0 <= c < 2:     s +=  3; r.append(f"flat {c:+.1f}%")

    # ── Buy/sell ratio ────────────────────────────
    total = d["buys_1h"] + d["sells_1h"]
    if total > 0:
        ratio = d["buys_1h"] / total
        if ratio > 0.75:   s += 20; r.append(f"💪 {ratio:.0%} buy pressure")
        elif ratio > 0.60: s += 12; r.append(f"buy dominant {ratio:.0%}")
        elif ratio > 0.50: s +=  5; r.append(f"slight buy {ratio:.0%}")
        elif ratio < 0.45: s -= 30; r.append(f"🔴 sell pressure {1-ratio:.0%}")

    # ── Liquidity ─────────────────────────────────
    if d["liquidity"] > 300_000:   s += 10; r.append("deep liq")
    elif d["liquidity"] > 100_000: s +=  8; r.append("good liq")
    elif d["liquidity"] > 30_000:  s +=  5; r.append("ok liq")
    elif d["liquidity"] > 10_000:  s +=  2; r.append("thin liq")

    # ── Age bonus ─────────────────────────────────
    age = d["age_hrs"]
    if age < 1:    s += 15; r.append("⚡ brand new (<1h)")
    elif age < 6:  s += 12; r.append(f"very fresh ({age:.1f}h)")
    elif age < 24: s +=  8; r.append(f"fresh ({age:.0f}h)")
    elif age < 48: s +=  3; r.append(f"young ({age:.0f}h)")

    # ── Market cap sweet spot for 20% scalp ──────
    mcap = d["mcap"]
    if 20_000 < mcap < 500_000:      s += 15; r.append(f"🎯 micro mcap ${mcap:,.0f}")
    elif 500_000 < mcap < 5_000_000: s += 10; r.append(f"small mcap ${mcap:,.0f}")
    elif 5_000_000 < mcap < 30_000_000: s += 5; r.append(f"mid mcap ${mcap:,.0f}")
    elif mcap > 50_000_000:          s -=  5; r.append(f"large mcap — less upside")

    # ── Vol/mcap ratio — money velocity ──────────
    if d["mcap"] > 0:
        vm = d["volume_24h"] / d["mcap"]
        if vm > 5:    s += 10; r.append(f"🚀 vol/mcap {vm:.1f}x — extremely hot")
        elif vm > 2:  s +=  6; r.append(f"vol/mcap {vm:.1f}x — hot")
        elif vm > 1:  s +=  3; r.append(f"vol/mcap {vm:.1f}x — active")

    # ── Multi-source confirmation ─────────────────
    if len(sources) >= 3: s += 15; r.append(f"🔥 confirmed {len(sources)} sources")
    elif len(sources) >= 2: s += 8; r.append(f"confirmed {len(sources)} sources")

    s = max(0, min(100, s))

    # Hard gates — prevent false BUY signals
    # 1. Must have positive 1h trend overall (not a dead cat bounce)
    # 2. Must have majority buyers
    # 3. Must not be in a downtrend on both timeframes
    buy_ratio      = d["buys_1h"] / max(1, d["buys_1h"] + d["sells_1h"])
    uptrend_1h     = d["change_1h"] >= 5    # meaningful positive 1h
    uptrend_5m     = d["change_5m"] >= 0    # not falling right now
    uptrend_24h    = d["change_24h"] >= -20 # not in a major downtrend
    buyers_winning = buy_ratio > 0.62       # clear majority buying
    not_both_red   = not (d["change_1h"] < -5 and d["change_5m"] < -3)

    # Fresh pump coins (<2h) get slightly looser gate — 5m can dip during consolidation
    is_fresh = d["age_hrs"] < 2
    
    if s >= 75 and uptrend_1h and buyers_winning and uptrend_24h:
        if uptrend_5m or is_fresh:
            sig = "🟢 BUY"
        else:
            sig = "🟡 WATCH"  # good score but 5m dipping — wait
    elif s >= 55 and not_both_red:
        sig = "🟡 WATCH"
    else:
        sig = "🔴 SKIP"
    return s, sig, r

# ━━ MAIN SCAN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def scan_once():
    now = datetime.now().strftime("%H:%M:%S")
    candidates = {}  # mint -> {data, sources}

    # Source 1: dexscreener trending/boosted
    trending_mints = fetch_dex_trending()
    for mint in trending_mints:
        if mint not in candidates:
            candidates[mint] = {"sources": []}
        candidates[mint]["sources"].append("dex_trending")

    # Source 2: coingecko trending solana tokens
    cg_mints = fetch_coingecko_trending()
    for mint in cg_mints:
        if mint not in candidates:
            candidates[mint] = {"sources": []}
        candidates[mint]["sources"].append("coingecko")

    # Source 3: smart wallet activity
    sw_activity = fetch_smart_wallet_activity()
    for item in sw_activity:
        mint = item["mint"]
        if mint not in candidates:
            candidates[mint] = {"sources": []}
        candidates[mint]["sources"].append(f"smart_wallet:{item['wallet']}")

    # Source 4: fresh pump.fun launches via token profiles — fetch BEFORE scoring
    pump_profile_mints = fetch_pump_profiles()
    for mint in pump_profile_mints:
        if mint not in candidates:
            candidates[mint] = {"sources": []}
        candidates[mint]["sources"].append("pump_fresh")

    # Source 5: brand new pairs (< 6h old)
    new_pair_mints = fetch_new_pairs()
    for mint in new_pair_mints:
        if mint not in candidates:
            candidates[mint] = {"sources": []}
        candidates[mint]["sources"].append("new_pair")

    # Fetch real data for all candidates
    results = []
    for mint, meta in candidates.items():
        d = fetch_dex_token(mint)
        if not d:
            continue
        # pump_fresh coins get looser filters — they are tiny by design
        is_pump = "pump_fresh" in meta["sources"]
        garbage = is_garbage_pump(d) if is_pump else is_garbage(d)
        if garbage:
            continue
        sc, sig, reasons = score_coin(d, meta["sources"])
        results.append({
            "d": d, "score": sc, "sig": sig,
            "reasons": reasons, "sources": meta["sources"]
        })
        time.sleep(0.3)  # be kind to APIs

    results.sort(key=lambda x: x["score"], reverse=True)

    # pump.fun early gems for display only
    pump_new      = fetch_pump_coins(PUMP_FUN_NEW)
    pump_trending = fetch_pump_coins(PUMP_FUN_TRENDING)

    # ── PRINT RESULTS ────────────────────────────────────
    print(f"\n{CY}{BD}╔══════════════════════════════════════╗{RS}")
    print(f"{CY}{BD}║  🔍 SCAN  {now}                    ║{RS}")

    buys   = [x for x in results if x["score"] >= 75]
    watches= [x for x in results if 60 <= x["score"] < 75]

    if buys:
        print(f"  {GR}{BD}🟢 BUY SIGNALS:{RS}")
        for e in buys[:5]:
            d = e["d"]
            key = f"{d['mint']}_{e['score']}"
            buy_ratio = d["buys_1h"] / max(1, d["buys_1h"] + d["sells_1h"])
            print(f"\n  {GR}{BD}  ▶  {d['name']}{RS} {DM}({d['mint'][:8]}...){RS}")
            print(f"     {CY}💲{d['price']:.8f}{RS}  mcap={DM}${d['mcap']:,.0f}{RS}  age={d['age_hrs']}h")
            print(f"     1h={GR}{d['change_1h']:+.1f}%{RS}  vol=${d['volume_24h']:,.0f}  liq=${d['liquidity']:,.0f}")
            print(f"     {GR}buys={d['buys_1h']}{RS}  {RD}sells={d['sells_1h']}{RS}  ratio={BD}{buy_ratio:.0%}{RS}")
            print(f"     score={YL}{BD}{e['score']}/100{RS} | {', '.join(e['reasons'])}")
            print(f"     {DM}sources: {', '.join(e['sources'])}{RS}")
            print(f"     🔗 {DM}{d['url']}{RS}")
            if key not in seen:
                brain.remember("scanner",
                    f"BUY {d['name']} @ ${d['price']:.8f} | score={e['score']} | "
                    f"mint={d['mint']} | mcap=${d['mcap']:,.0f} | age={d['age_hrs']}h | {', '.join(e['reasons'])}",
                    type="trade_signal", tags=f"{d['name'].lower()},buy,solana"
                )
                brain.share_idea("scanner",
                    f"TRADE ALERT: {d['name']} score={e['score']}/100 — {', '.join(e['reasons'][:3])}"
                )
                seen.add(key)
    else:
        print(f"  {DM}🟢 no buy signals this scan{RS}")

    if watches:
        print(f"\n  {YL}{BD}🟡 WATCHING:{RS}")
        for e in watches[:5]:
            d = e["d"]
            print(f"    {YL}{d['name']:<10}{RS} ${d['price']:.8f}  1h={d['change_1h']:+.1f}%  {BD}score={e['score']}/100{RS}  {DM}age={d['age_hrs']}h{RS}")

    # Pump.fun early gems
    early = [p for p in pump_new if 8_000 < p["mcap"] < 200_000 and p["vol"] > 3_000]
    if early:
        print(f"\n  {RD}{BD}💊 PUMP.FUN gems ({len(early)} found):{RS}")
        for p in early[:5]:
            print(f"    {RD}{p['name']:<10}{RS} mcap=${p['mcap']:,.0f}  vol=${p['vol']:,.0f}")
            brain.remember("scanner",
                f"PUMP early: {p['name']} mcap=${p['mcap']:,.0f} vol=${p['vol']:,.0f} mint={p['mint']}",
                type="pump_gem", tags="pump,early,solana"
            )

    total = len(results)
    print(f"\n{CY}╚══════════════════════════════════════╝{RS}")
    print(f"  {DM}📊 {total} scanned  {GR}{len(buys)} buys{RS}  {YL}{len(watches)} watching{RS}  {DM}next in {SCAN_INTERVAL}s{RS}")
    

def run():
    brain.init_db()
    print(f"{CY}{BD}🤖 BR0THER SCANNER v2{RS} — hunting alpha across all sources")
    print("   Sources: DexScreener trending, CoinGecko, Smart wallets, Pump.fun")
    print("   Filters: liq>$30k, vol>$50k, buys>20, not already pumped")
    print("   Press Ctrl+C to stop\n")
    scan_once()
    while True:
        try:
            time.sleep(SCAN_INTERVAL)
            scan_once()
        except KeyboardInterrupt:
            print("\n[scanner] stopped. signals saved to brain.")
            break
        except Exception as e:
            print(f"[scanner] error: {e} — retrying in {SCAN_INTERVAL}s")
            time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    run()
