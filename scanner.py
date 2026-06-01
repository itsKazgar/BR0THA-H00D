import requests
import time
from market_data import (
    fetch_top_solana_tokens, fetch_token_data, get_sol_price,
    gecko_trending_pools, gecko_new_pools,
    pumpfun_trending, pumpfun_latest,
    birdeye_trending_tokens, soltracker_new_tokens
)

TRENDING_SEARCHES = ["solana meme", "solana ai", "solana defi", "pump fun", "pepe solana"]

SKIP_SYMBOLS = {
    "USDT","USDC","USD1","DAI","BUSD","FRAX","TUSD",
    "WBTC","CBBTC","WETH","WBNB",
    "AAVE","LINK","UNI","CRV","MKR","CHZ","ENA","RENDER",
    "SOL","PYUSD","USAD","USDG","USDS","FDUSD","GUSD",
}

def fetch_dex_search(query):
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search/?q={query}",
            timeout=20, headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code != 200:
            return []
        return r.json().get("pairs", [])
    except:
        return []

def score_token(p):
    symbol    = p.get("baseToken", {}).get("symbol", "UNKNOWN").upper()
    mint      = p.get("baseToken", {}).get("address", "")
    if symbol in SKIP_SYMBOLS or len(symbol) > 12:
        return None
    liquidity = float(p.get("liquidity", {}).get("usd", 0) or 0)
    volume    = float(p.get("volume",    {}).get("h24", 0) or 0)
    change    = float(p.get("priceChange", {}).get("h24", 0) or 0)
    buys      = int(p.get("txns", {}).get("h24", {}).get("buys",  0) or 0)
    sells     = int(p.get("txns", {}).get("h24", {}).get("sells", 0) or 0)
    fdv       = float(p.get("fdv", 0) or 0)
    if liquidity < 50000 or volume < 25000:
        return None
    buy_pressure = buys / max(sells, 1)
    momentum = (change * 2.5) + (buy_pressure * 12) + (volume / 200000) + (liquidity / 500000)
    risk = 0
    if sells > buys:       risk += 10
    if liquidity < 100000: risk += 10
    if fdv > 1500000000:   risk += 20
    return {
        "token": symbol, "mint": mint, "score": round(momentum - risk, 2),
        "price": p.get("priceUsd"), "change_24h": round(change, 2),
        "volume": round(volume), "liquidity": round(liquidity),
        "fdv": round(fdv), "buy_pressure": round(buy_pressure, 2),
        "buys": buys, "sells": sells,
        "dex": p.get("dexId"), "pair": p.get("pairAddress"),
        "source": "dexscreener"
    }

def build_market():
    all_tokens   = []
    seen_pairs   = set()
    seen_symbols = set()

    # SOURCE 1: DexScreener trending searches
    print("  [SCAN] DexScreener...")
    for q in TRENDING_SEARCHES:
        pairs = fetch_dex_search(q)
        for p in pairs:
            try:
                addr   = p.get("pairAddress")
                symbol = p.get("baseToken", {}).get("symbol", "").upper()
                if not addr or addr in seen_pairs:
                    continue
                if p.get("chainId") != "solana":
                    continue
                seen_pairs.add(addr)
                scored = score_token(p)
                if scored and symbol not in seen_symbols:
                    seen_symbols.add(symbol)
                    all_tokens.append(scored)
            except:
                continue
        time.sleep(0.3)

    # SOURCE 2: CoinGecko top Solana tokens
    print("  [SCAN] CoinGecko...")
    for ct in fetch_top_solana_tokens(20):
        sym = ct.get("token", "").upper()
        if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
            continue
        seen_symbols.add(sym)
        dex = fetch_token_data(sym)
        if dex.get("error"):
            continue
        try:
            liquidity    = float(dex.get("liquidity") or 0)
            volume       = float(dex.get("volume_24h") or 0)
            change       = float(dex.get("price_change_24h") or 0)
            buys         = int(dex.get("buys_24h") or 0)
            sells        = int(dex.get("sells_24h") or 0)
            if liquidity < 50000 or volume < 25000:
                continue
            buy_pressure = buys / max(sells, 1)
            momentum     = (change * 2.5) + (buy_pressure * 12) + (volume / 200000) + (liquidity / 500000)
            risk = 0
            if sells > buys:       risk += 10
            if liquidity < 100000: risk += 10
            all_tokens.append({
                "token": sym, "mint": "", "score": round(momentum - risk, 2),
                "price": dex.get("price"), "change_24h": round(change, 2),
                "volume": round(volume), "liquidity": round(liquidity),
                "fdv": float(dex.get("fdv") or 0), "buy_pressure": round(buy_pressure, 2),
                "buys": buys, "sells": sells, "dex": dex.get("dex"),
                "source": "coingecko+dex", "market_cap": ct.get("market_cap", 0)
            })
        except:
            continue
        time.sleep(0.2)

    # SOURCE 3: GeckoTerminal trending (no key)
    print("  [SCAN] GeckoTerminal trending...")
    for gt in gecko_trending_pools(25):
        sym = gt.get("token", "").upper()[:12]
        if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
            continue
        liquidity = float(gt.get("liquidity") or 0)
        volume    = float(gt.get("volume_24h") or 0)
        change    = float(gt.get("price_change_24h") or 0)
        buys      = int(gt.get("buys_24h") or 0)
        sells     = int(gt.get("sells_24h") or 0)
        if liquidity < 50000 or volume < 25000:
            continue
        seen_symbols.add(sym)
        buy_pressure = buys / max(sells, 1)
        momentum     = (change * 2.5) + (buy_pressure * 12) + (volume / 200000) + (liquidity / 500000)
        risk = 0
        if sells > buys:       risk += 10
        if liquidity < 100000: risk += 10
        all_tokens.append({
            "token": sym, "mint": gt.get("mint", ""),
            "score": round(momentum - risk, 2),
            "price": gt.get("price"), "change_24h": round(change, 2),
            "volume": round(volume), "liquidity": round(liquidity),
            "fdv": float(gt.get("fdv") or 0), "buy_pressure": round(buy_pressure, 2),
            "buys": buys, "sells": sells, "dex": "gecko",
            "source": "geckoterminal_trending"
        })

    # SOURCE 4: GeckoTerminal new pools (no key) — early plays
    print("  [SCAN] GeckoTerminal new pools...")
    for gn in gecko_new_pools(20):
        sym = gn.get("token", "").upper()[:12]
        if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
            continue
        liquidity = float(gn.get("liquidity") or 0)
        if liquidity < 10000:
            continue
        seen_symbols.add(sym)
        all_tokens.append({
            "token": sym, "mint": gn.get("mint", ""),
            "score": 6.0,
            "price": gn.get("price"), "change_24h": 0,
            "volume": 0, "liquidity": round(liquidity),
            "fdv": float(gn.get("fdv") or 0), "buy_pressure": 1.0,
            "buys": 0, "sells": 0, "dex": "gecko_new",
            "source": "geckoterminal_new",
            "new_listing": True,
            "created_at": gn.get("created_at", "")
        })

    # SOURCE 5: Pump.fun trending (no key) — what CT is aping
    print("  [SCAN] Pump.fun trending...")
    for pf in pumpfun_trending(20):
        sym = pf.get("token", "").upper()[:12]
        if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
            continue
        mcap = float(pf.get("market_cap") or 0)
        if mcap < 10000:
            continue
        seen_symbols.add(sym)
        all_tokens.append({
            "token": sym, "mint": pf.get("mint", ""),
            "score": min(mcap / 10000, 50),  # score based on mcap
            "price": None, "change_24h": 0,
            "volume": 0, "liquidity": 0,
            "fdv": mcap, "buy_pressure": 1.0,
            "buys": 0, "sells": 0, "dex": "pumpfun",
            "replies": pf.get("replies", 0),
            "source": "pumpfun_trending"
        })

    # SOURCE 6: Pump.fun latest launches (no key) — first seconds
    print("  [SCAN] Pump.fun new launches...")
    for pl in pumpfun_latest(15):
        sym = pl.get("token", "").upper()[:12]
        if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
            continue
        seen_symbols.add(sym)
        all_tokens.append({
            "token": sym, "mint": pl.get("mint", ""),
            "score": 3.0,
            "price": pl.get("price"), "change_24h": 0,
            "volume": 0, "liquidity": float(pl.get("liquidity") or 0),
            "fdv": float(pl.get("market_cap") or 0), "buy_pressure": 1.0,
            "buys": 0, "sells": 0, "dex": "pumpfun_new",
            "source": "pumpfun_new",
            "new_listing": True
        })

    # SOURCE 7: Birdeye trending (needs key — skips silently if no key)
    if True:
        print("  [SCAN] Birdeye trending...")
        for bt in birdeye_trending_tokens(25):
            sym = bt.get("token", "").upper()
            if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
                continue
            liquidity = float(bt.get("liquidity") or 0)
            volume    = float(bt.get("volume_24h") or 0)
            if liquidity < 50000 or volume < 25000:
                continue
            seen_symbols.add(sym)
            buys  = int(bt.get("buy_count") or 0)
            sells = int(bt.get("sell_count") or 0)
            buy_pressure = buys / max(sells, 1)
            change       = float(bt.get("price_change_24h") or 0)
            momentum     = (change * 2.5) + (buy_pressure * 12) + (volume / 200000) + (liquidity / 500000)
            risk = 0
            if sells > buys:       risk += 10
            if liquidity < 100000: risk += 10
            all_tokens.append({
                "token": sym, "mint": bt.get("mint", ""),
                "score": round(momentum - risk, 2),
                "price": bt.get("price"), "change_24h": round(change, 2),
                "volume": round(volume), "liquidity": round(liquidity),
                "fdv": 0, "buy_pressure": round(buy_pressure, 2),
                "buys": buys, "sells": sells, "dex": "birdeye",
                "holder_count": bt.get("holder_count", 0),
                "source": "birdeye_trending"
            })

    # SOURCE 8: Solana Tracker (needs key — skips silently if no key)
    print("  [SCAN] Solana Tracker new...")
    for st in soltracker_new_tokens(20):
        sym = st.get("token", "").upper()
        if not sym or sym in seen_symbols or sym in SKIP_SYMBOLS:
            continue
        liquidity = float(st.get("liquidity") or 0)
        if liquidity < 10000:
            continue
        seen_symbols.add(sym)
        all_tokens.append({
            "token": sym, "mint": st.get("mint", ""),
            "score": 5.0,
            "price": st.get("price"), "change_24h": 0,
            "volume": 0, "liquidity": round(liquidity),
            "fdv": 0, "buy_pressure": 1.0,
            "buys": 0, "sells": 0, "dex": "new_listing",
            "source": "solana_tracker_new",
            "new_listing": True
        })

    ranked = sorted(all_tokens, key=lambda x: x["score"], reverse=True)
    return [t for t in ranked if t["score"] > 0][:40]

def print_market(results):
    sol = get_sol_price()
    print(f"\n=== BR0THA LIVE FLOW | SOL=${sol} ===\n")
    sources = {}
    for r in results:
        s = r.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1
    print(f"Sources: {sources}\n")
    for i, r in enumerate(results, 1):
        print(f"{i:2}. {r['token']:12} | SCORE {r['score']:8.2f} | {r['source']}")
        print(f"    Price: ${r['price']} | 24h: {r['change_24h']}%")
        print(f"    Vol: ${r['volume']:,} | Liq: ${r['liquidity']:,}")
        print(f"    Buys/Sells: {r['buys']}/{r['sells']} | BP: {r['buy_pressure']}")
        if r.get("mint"):
            print(f"    Mint: {r['mint'][:20]}...")
        print()

if __name__ == "__main__":
    market = build_market()
    print_market(market)
