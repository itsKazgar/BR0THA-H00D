import requests
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ─────────────────────────────────────────────
# DEXSCREENER
# ─────────────────────────────────────────────

def fetch_dexscreener_trending():

    try:

        r = requests.get(
            "https://api.dexscreener.com/latest/dex/search/?q=solana",
            headers=HEADERS,
            timeout=20
        )

        data = r.json()

        pairs = data.get("pairs", [])

        out = []

        for p in pairs[:50]:

            try:

                out.append({
                    "source": "dexscreener",
                    "token": p["baseToken"]["symbol"],
                    "price": p.get("priceUsd"),
                    "volume_24h": p.get("volume", {}).get("h24"),
                    "liquidity": p.get("liquidity", {}).get("usd"),
                    "fdv": p.get("fdv"),
                    "change_24h": p.get("priceChange", {}).get("h24"),
                    "dex": p.get("dexId"),
                    "pair": p.get("pairAddress"),
                })

            except:
                pass

        return out

    except:
        return []


# ─────────────────────────────────────────────
# COINGECKO TRENDING
# ─────────────────────────────────────────────

def fetch_coingecko_trending():

    try:

        r = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            headers=HEADERS,
            timeout=20
        )

        data = r.json()

        coins = data.get("coins", [])

        out = []

        for c in coins:

            item = c.get("item", {})

            out.append({
                "source": "coingecko",
                "token": item.get("symbol"),
                "name": item.get("name"),
                "market_cap_rank": item.get("market_cap_rank"),
            })

        return out

    except:
        return []


# ─────────────────────────────────────────────
# PUMP.FUN DISCOVERY
# ─────────────────────────────────────────────

def fetch_pumpfun_candidates():

    try:

        r = requests.get(
            "https://frontend-api.pump.fun/coins/king-of-the-hill",
            headers=HEADERS,
            timeout=20
        )

        data = r.json()

        if not isinstance(data, list):
            return []

        out = []

        for coin in data[:20]:

            out.append({
                "source": "pumpfun",
                "token": coin.get("symbol"),
                "name": coin.get("name"),
                "market_cap": coin.get("usd_market_cap"),
                "volume": coin.get("volume_24h"),
            })

        return out

    except:
        return []


# ─────────────────────────────────────────────
# MASTER MARKET VIEW
# ─────────────────────────────────────────────

def build_market_view():

    market = {
        "dexscreener": fetch_dexscreener_trending(),
        "coingecko": fetch_coingecko_trending(),
        "pumpfun": fetch_pumpfun_candidates(),
    }

    return market


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":

    market = build_market_view()

    print("\n=== DEXSCREENER ===\n")

    for x in market["dexscreener"][:10]:
        print(x)

    print("\n=== COINGECKO TRENDING ===\n")

    for x in market["coingecko"][:10]:
        print(x)

    print("\n=== PUMPFUN ===\n")

    for x in market["pumpfun"][:10]:
        print(x)
