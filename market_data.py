import requests
import os
from dotenv import load_dotenv
load_dotenv(override=True)

HELIUS_KEY     = os.getenv("HELIUS_API_KEY", "")
BIRDEYE_KEY    = os.getenv("BIRDEYE_API_KEY", "")
SOLTRACKER_KEY = os.getenv("SOLTRACKER_API_KEY", "")

HELIUS_RPC     = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"
DEX_URL        = "https://api.dexscreener.com/latest/dex/search/?q="
COINGECKO_URL  = "https://api.coingecko.com/api/v3"
BIRDEYE_URL    = "https://public-api.birdeye.so"
SOLTRACKER_URL = "https://data.solanatracker.io"
SOL_RPC        = "https://api.mainnet-beta.solana.com"
GECKO_URL      = "https://api.geckoterminal.com/api/v2"
JUPITER_URL    = "https://price.jup.ag/v4"
RUGCHECK_URL   = "https://api.rugcheck.xyz/v1"
PUMPFUN_URL    = "https://client-proxy-server.pump.fun/coins"

HEADERS        = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
HEADERS_BIRDEYE  = {"X-API-KEY": BIRDEYE_KEY, "x-chain": "solana"}
HEADERS_SOLTRACK = {"x-api-key": SOLTRACKER_KEY}

# ── DEXSCREENER ────────────────────────────────────────────────────────────────
def fetch_token_data(token):
    try:
        r = requests.get(DEX_URL + token, headers=HEADERS, timeout=20)
        data = r.json()
        pairs = data.get("pairs", [])
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        p = sol_pairs[0] if sol_pairs else (pairs[0] if pairs else None)
        if not p:
            return {"error": "No pairs found"}
        return {
            "token": token,
            "price": p.get("priceUsd"),
            "volume_24h": p.get("volume", {}).get("h24"),
            "liquidity": p.get("liquidity", {}).get("usd"),
            "fdv": p.get("fdv"),
            "chain": p.get("chainId"),
            "dex": p.get("dexId"),
            "pair": p.get("pairAddress"),
            "price_change_24h": p.get("priceChange", {}).get("h24"),
            "buys_24h": p.get("txns", {}).get("h24", {}).get("buys"),
            "sells_24h": p.get("txns", {}).get("h24", {}).get("sells"),
        }
    except Exception as e:
        return {"error": str(e)}

# ── JUPITER PRICE API — most accurate Solana prices, no key ───────────────────
def jupiter_price(mint_address):
    if not mint_address:
        return {}
    try:
        r = requests.get(
            f"{JUPITER_URL}/price",
            params={"ids": mint_address},
            headers=HEADERS,
            timeout=10
        )
        if r.status_code != 200:
            return {}
        data = r.json().get("data", {}).get(mint_address, {})
        return {
            "price":      data.get("price"),
            "mint":       mint_address,
            "source":     "jupiter"
        }
    except:
        return {}

# ── RUGCHECK.XYZ — full rug report, no key ────────────────────────────────────
def rugcheck_report(mint_address):
    if not mint_address:
        return {}
    try:
        r = requests.get(
            f"{RUGCHECK_URL}/tokens/{mint_address}/report/summary",
            headers=HEADERS,
            timeout=15
        )
        if r.status_code != 200:
            return {}
        d = r.json()
        risks = d.get("risks", [])
        return {
            "score":        d.get("score", 0),
            "score_label":  d.get("score_normalised", ""),
            "risks":        risks,
            "risk_count":   len(risks),
            "top_holders":  d.get("topHolders", []),
            "markets":      d.get("markets", []),
            "lp_locked":    any("locked" in str(r).lower() for r in risks),
            "mint_disabled": any("mint" in str(r).lower() and "disabled" in str(r).lower() for r in risks),
            "source":       "rugcheck"
        }
    except:
        return {}

# ── GECKOTERMINAL — new pools + trending, no key ──────────────────────────────
def gecko_new_pools(limit=20):
    try:
        r = requests.get(
            f"{GECKO_URL}/networks/solana/new_pools",
            params={"page": 1},
            headers=HEADERS,
            timeout=15
        )
        if r.status_code != 200:
            return []
        pools = r.json().get("data", [])
        results = []
        for p in pools[:limit]:
            attr = p.get("attributes", {})
            rel  = p.get("relationships", {})
            base = rel.get("base_token", {}).get("data", {})
            results.append({
                "token":            attr.get("name", "").upper(),
                "mint":             base.get("id", "").replace("solana_", ""),
                "price":            attr.get("base_token_price_usd"),
                "volume_24h":       attr.get("volume_usd", {}).get("h24"),
                "liquidity":        attr.get("reserve_in_usd"),
                "price_change_24h": attr.get("price_change_percentage", {}).get("h24"),
                "created_at":       attr.get("pool_created_at", ""),
                "fdv":              attr.get("fdv_usd"),
                "source":           "geckoterminal_new"
            })
        return results
    except:
        return []

def gecko_trending_pools(limit=20):
    try:
        r = requests.get(
            f"{GECKO_URL}/networks/solana/trending_pools",
            params={"page": 1},
            headers=HEADERS,
            timeout=15
        )
        if r.status_code != 200:
            return []
        pools = r.json().get("data", [])
        results = []
        for p in pools[:limit]:
            attr = p.get("attributes", {})
            rel  = p.get("relationships", {})
            base = rel.get("base_token", {}).get("data", {})
            results.append({
                "token":            attr.get("name", "").split("/")[0].strip().upper(),
                "mint":             base.get("id", "").replace("solana_", ""),
                "price":            attr.get("base_token_price_usd"),
                "volume_24h":       attr.get("volume_usd", {}).get("h24"),
                "liquidity":        attr.get("reserve_in_usd"),
                "price_change_24h": attr.get("price_change_percentage", {}).get("h24"),
                "fdv":              attr.get("fdv_usd"),
                "buys_24h":         attr.get("transactions", {}).get("h24", {}).get("buys"),
                "sells_24h":        attr.get("transactions", {}).get("h24", {}).get("sells"),
                "source":           "geckoterminal_trending"
            })
        return results
    except:
        return []

# ── PUMP.FUN — catch tokens at launch before they hit DEX, no key ─────────────
def pumpfun_latest(limit=20):
    try:
        r = requests.get(
            f"{PUMPFUN_URL}/coins",
            params={"limit": limit, "sort": "created_timestamp", "order": "DESC", "includeNsfw": False},
            headers=HEADERS,
            timeout=15
        )
        if r.status_code != 200:
            return []
        coins = r.json() if isinstance(r.json(), list) else r.json().get("coins", [])
        results = []
        for c in coins:
            results.append({
                "token":      c.get("symbol", "").upper(),
                "mint":       c.get("mint", ""),
                "name":       c.get("name", ""),
                "price":      c.get("usd_market_cap", 0) / max(c.get("total_supply", 1), 1),
                "market_cap": c.get("usd_market_cap", 0),
                "liquidity":  c.get("virtual_sol_reserves", 0),
                "replies":    c.get("reply_count", 0),
                "created_at": c.get("created_timestamp", ""),
                "source":     "pumpfun"
            })
        return results
    except:
        return []

def pumpfun_trending(limit=20):
    try:
        r = requests.get(
            f"{PUMPFUN_URL}/coins",
            params={"limit": limit, "sort": "market_cap", "order": "DESC", "includeNsfw": False},
            headers=HEADERS,
            timeout=15
        )
        if r.status_code != 200:
            return []
        coins = r.json() if isinstance(r.json(), list) else r.json().get("coins", [])
        results = []
        for c in coins:
            results.append({
                "token":      c.get("symbol", "").upper(),
                "mint":       c.get("mint", ""),
                "name":       c.get("name", ""),
                "market_cap": c.get("usd_market_cap", 0),
                "replies":    c.get("reply_count", 0),
                "source":     "pumpfun_trending"
            })
        return results
    except:
        return []

# ── COINGECKO ──────────────────────────────────────────────────────────────────
def fetch_top_solana_tokens(limit=20):
    try:
        r = requests.get(
            COINGECKO_URL + "/coins/markets",
            params={
                "vs_currency": "usd",
                "category": "solana-ecosystem",
                "order": "volume_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": False
            },
            headers=HEADERS,
            timeout=15
        )
        if r.status_code != 200:
            return []
        return [{
            "token":            c.get("symbol", "").upper(),
            "name":             c.get("name"),
            "price":            c.get("current_price"),
            "volume_24h":       c.get("total_volume"),
            "market_cap":       c.get("market_cap"),
            "price_change_24h": c.get("price_change_percentage_24h"),
            "source":           "coingecko"
        } for c in r.json()]
    except:
        return []

def get_sol_price():
    try:
        r = requests.get(
            COINGECKO_URL + "/simple/price",
            params={"ids": "solana", "vs_currencies": "usd"},
            headers=HEADERS,
            timeout=10
        )
        return r.json().get("solana", {}).get("usd", 0)
    except:
        return 0

# ── HELIUS ─────────────────────────────────────────────────────────────────────
def get_token_metadata_helius(mint_address):
    if not HELIUS_KEY or not mint_address:
        return {}
    try:
        r = requests.post(HELIUS_RPC, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getAsset",
            "params": {"id": mint_address}
        }, timeout=15)
        res       = r.json().get("result", {})
        content   = res.get("content", {})
        authority = res.get("authorities", [{}])
        ownership = res.get("ownership", {})
        return {
            "name":                   content.get("metadata", {}).get("name", ""),
            "symbol":                 content.get("metadata", {}).get("symbol", ""),
            "freeze_authority":       authority[0].get("address", None) if authority else None,
            "owner":                  ownership.get("owner", ""),
            "supply":                 res.get("token_info", {}).get("supply", 0),
            "decimals":               res.get("token_info", {}).get("decimals", 0),
            "mint_authority_revoked": res.get("mint_extensions") is None,
            "source":                 "helius_das"
        }
    except:
        return {}

def get_holder_concentration(mint_address):
    if not mint_address:
        return {}
    try:
        supply_r = requests.post(SOL_RPC, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenSupply",
            "params": [mint_address]
        }, timeout=15)
        total_supply = float(
            supply_r.json().get("result", {})
            .get("value", {}).get("uiAmount", 0) or 0
        )
        holders_r = requests.post(SOL_RPC, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [mint_address]
        }, timeout=15)
        holders = holders_r.json().get("result", {}).get("value", [])
        if not holders or total_supply == 0:
            return {}
        top_amounts = [float(h.get("uiAmount") or 0) for h in holders[:10]]
        top_total   = sum(top_amounts)
        top_pct     = (top_total / total_supply) * 100 if total_supply else 0
        top1_pct    = (top_amounts[0] / total_supply * 100) if top_amounts else 0
        return {
            "holder_count":       len(holders),
            "top10_pct":          round(top_pct, 1),
            "top1_pct":           round(top1_pct, 1),
            "concentration_risk": top_pct > 60,
            "top1_risk":          top1_pct > 20,
            "source":             "solana_foundation_rpc"
        }
    except:
        return {}

# ── BIRDEYE (needs key) ────────────────────────────────────────────────────────
def birdeye_token_overview(mint_address):
    if not BIRDEYE_KEY or not mint_address:
        return {}
    try:
        r = requests.get(
            f"{BIRDEYE_URL}/defi/token_overview",
            params={"address": mint_address},
            headers=HEADERS_BIRDEYE,
            timeout=15
        )
        if r.status_code != 200:
            return {}
        d = r.json().get("data", {})
        return {
            "price":           d.get("price"),
            "volume_24h":      d.get("v24hUSD"),
            "liquidity":       d.get("liquidity"),
            "holder_count":    d.get("holder"),
            "buy_count_24h":   d.get("buy24h"),
            "sell_count_24h":  d.get("sell24h"),
            "unique_wallets":  d.get("uniqueWallet24h"),
            "fdv":             d.get("fdv"),
            "source":          "birdeye"
        }
    except:
        return {}

def birdeye_security_check(mint_address):
    if not BIRDEYE_KEY or not mint_address:
        return {}
    try:
        r = requests.get(
            f"{BIRDEYE_URL}/defi/token_security",
            params={"address": mint_address},
            headers=HEADERS_BIRDEYE,
            timeout=15
        )
        if r.status_code != 200:
            return {}
        d = r.json().get("data", {})
        return {
            "mint_authority_disabled":    d.get("mintAuthorityDisabled", False),
            "freeze_authority_disabled":  d.get("freezeAuthorityDisabled", False),
            "top10_holder_pct":           d.get("top10HolderPercent"),
            "lp_locked_pct":              d.get("lpLockPercent"),
            "source":                     "birdeye_security"
        }
    except:
        return {}

def birdeye_trending_tokens(limit=20):
    if not BIRDEYE_KEY:
        return []
    try:
        r = requests.get(
            f"{BIRDEYE_URL}/defi/token_trending",
            params={"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": limit},
            headers=HEADERS_BIRDEYE,
            timeout=15
        )
        if r.status_code != 200:
            return []
        tokens = r.json().get("data", {}).get("tokens", [])
        return [{
            "token":            t.get("symbol", "").upper(),
            "mint":             t.get("address", ""),
            "price":            t.get("price"),
            "volume_24h":       t.get("v24hUSD"),
            "liquidity":        t.get("liquidity"),
            "price_change_24h": t.get("priceChange24hPercent"),
            "buy_count":        t.get("buy24h"),
            "sell_count":       t.get("sell24h"),
            "holder_count":     t.get("holder"),
            "source":           "birdeye_trending"
        } for t in tokens]
    except:
        return []

# ── SOLANA TRACKER (needs key) ─────────────────────────────────────────────────
def soltracker_new_tokens(limit=20):
    if not SOLTRACKER_KEY:
        return []
    try:
        r = requests.get(
            f"{SOLTRACKER_URL}/tokens/new",
            params={"limit": limit},
            headers=HEADERS_SOLTRACK,
            timeout=15
        )
        if r.status_code != 200:
            return []
        data   = r.json()
        tokens = data if isinstance(data, list) else data.get("tokens", [])
        results = []
        for t in tokens:
            token_info = t.get("token", t)
            pool_info  = t.get("pools", [{}])[0] if t.get("pools") else {}
            results.append({
                "token":      token_info.get("symbol", "").upper(),
                "mint":       token_info.get("mint", ""),
                "name":       token_info.get("name", ""),
                "price":      pool_info.get("price", {}).get("usd"),
                "liquidity":  pool_info.get("liquidity", {}).get("usd"),
                "market_cap": pool_info.get("marketCap", {}).get("usd"),
                "created_at": token_info.get("createdAt", ""),
                "source":     "solana_tracker_new"
            })
        return results
    except:
        return []

def soltracker_token_stats(mint_address):
    if not SOLTRACKER_KEY or not mint_address:
        return {}
    try:
        r = requests.get(
            f"{SOLTRACKER_URL}/tokens/{mint_address}",
            headers=HEADERS_SOLTRACK,
            timeout=15
        )
        if r.status_code != 200:
            return {}
        d     = r.json()
        token = d.get("token", {})
        pools = d.get("pools", [{}])
        pool  = pools[0] if pools else {}
        return {
            "name":         token.get("name", ""),
            "symbol":       token.get("symbol", "").upper(),
            "holder_count": token.get("holders", 0),
            "price":        pool.get("price", {}).get("usd"),
            "liquidity":    pool.get("liquidity", {}).get("usd"),
            "lp_burned":    pool.get("lpBurn", 0),
            "risks":        d.get("risks", []),
            "source":       "solana_tracker"
        }
    except:
        return {}

# ── ENRICH — full pipeline ─────────────────────────────────────────────────────
def enrich_token(symbol, mint_address=None):
    """
    Full enrichment — all available sources merged into one dict.
    No-key sources always run. Keyed sources run if key is present.
    """
    print(f"  [ENRICH] {symbol} | mint={mint_address[:12] if mint_address else 'none'}...")
    result = {"token": symbol, "mint": mint_address or ""}

    # 1. DexScreener — baseline (no key)
    dex = fetch_token_data(mint_address or symbol)
    if not dex.get("error"):
        result.update(dex)

    # 2. Jupiter price — most accurate (no key)
    if mint_address:
        jup = jupiter_price(mint_address)
        if jup.get("price"):
            result["jupiter_price"] = jup["price"]
            if not result.get("price"):
                result["price"] = jup["price"]

    # 3. Rugcheck — full rug report (no key)
    if mint_address:
        rug = rugcheck_report(mint_address)
        if rug:
            result["rugcheck"]       = rug
            result["rugcheck_score"] = rug.get("score", 0)
            result["rugcheck_risks"] = rug.get("risks", [])
            result["lp_locked"]      = rug.get("lp_locked", False)

    # 4. Helius DAS — on-chain metadata (needs key)
    if mint_address and HELIUS_KEY:
        helius_meta = get_token_metadata_helius(mint_address)
        if helius_meta:
            result["helius"] = helius_meta
            result["mint_authority_revoked"] = helius_meta.get("mint_authority_revoked", False)

    # 5. Solana Foundation RPC — holder concentration (no key)
    if mint_address:
        concentration = get_holder_concentration(mint_address)
        if concentration:
            result["concentration"] = concentration
            result["top10_pct"]     = concentration.get("top10_pct", 0)

    # 6. Birdeye — richer market data + security (needs key)
    if mint_address and BIRDEYE_KEY:
        bd_overview = birdeye_token_overview(mint_address)
        bd_security = birdeye_security_check(mint_address)
        if bd_overview:
            result["birdeye"]      = bd_overview
            result["holder_count"] = bd_overview.get("holder_count", 0)
        if bd_security:
            result["security"]                  = bd_security
            result["mint_authority_disabled"]   = bd_security.get("mint_authority_disabled", False)
            result["freeze_authority_disabled"] = bd_security.get("freeze_authority_disabled", False)
            result["lp_locked_pct"]             = bd_security.get("lp_locked_pct", 0)
            result["top10_holder_pct"]          = bd_security.get("top10_holder_pct", 0)

    # 7. Solana Tracker (needs key)
    if mint_address and SOLTRACKER_KEY:
        st_stats = soltracker_token_stats(mint_address)
        if st_stats:
            result["soltracker"]   = st_stats
            result["holder_count"] = result.get("holder_count") or st_stats.get("holder_count", 0)
            result["lp_burned"]    = st_stats.get("lp_burned", 0)

    return result

if __name__ == "__main__":
    print("SOL price:", get_sol_price())
    print("\nTop CoinGecko tokens:", [t["token"] for t in fetch_top_solana_tokens(5)])
    print("\nGeckoTerminal trending:")
    for t in gecko_trending_pools(3):
        print(f"  {t['token']} | ${t['price']} | vol=${t['volume_24h']} | liq=${t['liquidity']}")
    print("\nGeckoTerminal new pools:")
    for t in gecko_new_pools(3):
        print(f"  {t['token']} | liq=${t['liquidity']} | created={t['created_at'][:10]}")
    print("\nPump.fun trending:")
    for t in pumpfun_trending(3):
        print(f"  {t['token']} | mcap=${t['market_cap']} | replies={t['replies']}")
    print("\nPump.fun latest launches:")
    for t in pumpfun_latest(3):
        print(f"  {t['token']} | {t['mint'][:12]}...")
