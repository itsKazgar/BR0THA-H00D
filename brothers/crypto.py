import requests

NAME        = "Crypto Brother"
DESCRIPTION = "Live crypto prices and fear & greed index"
ENABLED     = True
COMMANDS    = ["price <symbol>", "sol", "fear", "greed"]

def _sol():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=6)
        return float(r.json()["solana"]["usd"])
    except:
        return None

def _token(symbol):
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/search?q={symbol}", timeout=8)
        pairs = [p for p in r.json().get("pairs", [])
                 if p.get("chainId") == "solana"
                 and p.get("baseToken", {}).get("symbol", "").upper() == symbol.upper()]
        if not pairs:
            return None
        best = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
        return {
            "price":      float(best.get("priceUsd", 0) or 0),
            "change_1h":  float(best.get("priceChange", {}).get("h1", 0) or 0),
            "change_24h": float(best.get("priceChange", {}).get("h24", 0) or 0),
            "mcap":       float(best.get("marketCap", 0) or 0),
        }
    except:
        return None

def _fg():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        d = r.json()["data"][0]
        return f"{d['value']} ({d['value_classification']})"
    except:
        return None

def run(user_input):
    lower = user_input.lower().strip()
    if lower in ["sol", "solana", "sol price", "btc", "bitcoin", "eth", "ethereum"]:
        p = _sol()
        return f"◎ SOL: ${p:,.2f}" if p else "Could not fetch SOL."
    if lower in ["fear", "greed", "fear greed", "market mood"]:
        fg = _fg()
        return f"😨 Fear & Greed: {fg}" if fg else "Could not fetch."
    if lower.startswith("price "):
        sym = lower.replace("price ", "").strip().upper()
        if sym == "SOL":
            p = _sol()
            return f"◎ SOL: ${p:,.2f}" if p else "Could not fetch."
        d = _token(sym)
        if d:
            return (f"{sym}: ${d['price']:.8f} | 1h: {d['change_1h']:+.1f}% | "
                    f"24h: {d['change_24h']:+.1f}% | mcap: ${d['mcap']:,.0f}")
        return f"Could not find {sym} on Solana."
    return None
