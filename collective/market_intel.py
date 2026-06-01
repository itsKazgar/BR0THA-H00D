"""
market_intel.py — Full free data stack for BrothaBot
Sources: CoinGecko, DexScreener, Helius, Solana RPC, Magic Eden
"""
import os, requests, logging
from dotenv import load_dotenv
load_dotenv('/home/kazgar/BR0THA_bot/.env')

logger = logging.getLogger(__name__)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY","")
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

HEADERS = {"User-Agent": "BrothaBot/1.0"}

def get_global_market() -> dict:
    """CoinGecko global crypto market stats."""
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", headers=HEADERS, timeout=8)
        d = r.json().get("data", {})
        return {
            "total_mcap": d.get("total_market_cap", {}).get("usd", 0),
            "total_volume": d.get("total_volume", {}).get("usd", 0),
            "btc_dominance": d.get("market_cap_percentage", {}).get("btc", 0),
            "sol_dominance": d.get("market_cap_percentage", {}).get("sol", 0),
            "market_cap_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
            "active_coins": d.get("active_cryptocurrencies", 0),
        }
    except Exception as e:
        logger.error(f"Global market error: {e}")
        return {}

def get_sol_prices() -> dict:
    """Get SOL ecosystem token prices."""
    try:
        ids = "solana,bitcoin,ethereum,bonk,jup-governance-token,raydium,orca,tensor,pyth-network,wormhole,jito-governance-token"
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true",
            headers=HEADERS, timeout=8
        )
        return r.json()
    except Exception as e:
        logger.error(f"SOL prices error: {e}")
        return {}

def get_dex_trending() -> list:
    """DexScreener trending token profiles on Solana."""
    try:
        prof = requests.get("https://api.dexscreener.com/token-profiles/latest/v1", headers=HEADERS, timeout=8).json()
        sol_tokens = [p for p in (prof if isinstance(prof, list) else []) if p.get("chainId") == "solana"][:8]
        if not sol_tokens:
            return []
        mints = "%2C".join([p.get("tokenAddress","") for p in sol_tokens if p.get("tokenAddress")])
        pairs_r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mints}", headers=HEADERS, timeout=8).json()
        pairs = pairs_r.get("pairs") or []
        seen = set()
        result = []
        for p in pairs:
            sym = p.get("baseToken",{}).get("symbol","?")
            if sym in seen or sym in ["SOL","USDC","USDT","WSOL"]:
                continue
            seen.add(sym)
            result.append({
                "symbol": sym,
                "price": p.get("priceUsd","?"),
                "change_24h": float(p.get("priceChange",{}).get("h24",0) or 0),
                "volume_24h": float(p.get("volume",{}).get("h24",0) or 0),
                "mcap": float(p.get("marketCap") or p.get("fdv") or 0),
                "mint": p.get("baseToken",{}).get("address",""),
            })
        return sorted(result, key=lambda x: x["volume_24h"], reverse=True)[:6]
    except Exception as e:
        logger.error(f"DexScreener trending error: {e}")
        return []

def get_dex_boosted() -> list:
    """DexScreener boosted tokens — paid promotions = someone believes in these."""
    try:
        r = requests.get("https://api.dexscreener.com/token-boosts/top/v1", headers=HEADERS, timeout=8).json()
        sol = [p for p in (r if isinstance(r, list) else []) if p.get("chainId") == "solana"][:5]
        return [{"symbol": p.get("description","?")[:20], "mint": p.get("tokenAddress",""), "amount": p.get("totalAmount",0)} for p in sol]
    except Exception as e:
        logger.error(f"DexScreener boosted error: {e}")
        return []

def get_new_solana_pairs() -> list:
    """DexScreener newest Solana pairs — fresh launches."""
    try:
        r = requests.get("https://api.dexscreener.com/latest/dex/search?q=solana", headers=HEADERS, timeout=8).json()
        pairs = r.get("pairs", [])
        fresh = [p for p in pairs
                 if p.get("chainId") == "solana"
                 and p.get("baseToken",{}).get("symbol","") not in ["SOL","USDC","USDT","WSOL"]
                 and float(p.get("volume",{}).get("h24",0) or 0) > 5000]
        fresh = sorted(fresh, key=lambda x: x.get("pairCreatedAt",0) or 0, reverse=True)[:5]
        return [{
            "symbol": p.get("baseToken",{}).get("symbol","?"),
            "price": p.get("priceUsd","?"),
            "change_24h": float(p.get("priceChange",{}).get("h24",0) or 0),
            "volume_24h": float(p.get("volume",{}).get("h24",0) or 0),
            "age_hours": round(((__import__('time').time()*1000) - (p.get("pairCreatedAt") or 0)) / 3600000, 1),
        } for p in fresh]
    except Exception as e:
        logger.error(f"New pairs error: {e}")
        return []

def get_coingecko_trending() -> list:
    """CoinGecko trending with price change data."""
    try:
        r = requests.get("https://api.coingecko.com/api/v3/search/trending", headers=HEADERS, timeout=8).json()
        coins = r.get("coins", [])
        return [{
            "symbol": c["item"]["symbol"],
            "name": c["item"]["name"],
            "rank": c["item"].get("market_cap_rank", 0),
            "change_24h": c["item"].get("data",{}).get("price_change_percentage_24h",{}).get("usd", 0),
            "price": c["item"].get("data",{}).get("price","?"),
        } for c in coins[:7]]
    except Exception as e:
        logger.error(f"CoinGecko trending error: {e}")
        return []

def get_magic_eden_trending() -> list:
    """Magic Eden top Solana NFT collections."""
    try:
        r = requests.get(
            "https://api-mainnet.magiceden.dev/v2/marketplaces/solana/popular_collections?timeRange=1d&limit=5",
            headers=HEADERS, timeout=8
        )
        if r.status_code != 200:
            return []
        cols = r.json()
        return [{
            "name": c.get("name","?"),
            "floor": c.get("floorPrice",0) / 1e9,
            "volume": c.get("volumeAll",0) / 1e9,
        } for c in cols[:5]]
    except Exception as e:
        logger.error(f"Magic Eden error: {e}")
        return []

def get_solana_network_stats() -> dict:
    """Live Solana network stats via public RPC."""
    try:
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json={"jsonrpc":"2.0","id":1,"method":"getRecentPerformanceSamples","params":[1]},
            timeout=8
        )
        samples = r.json().get("result", [])
        if samples:
            s = samples[0]
            tps = round(s.get("numTransactions",0) / s.get("samplePeriodSecs",60), 0)
            return {"tps": tps, "slot": s.get("slot",0)}
        return {}
    except Exception as e:
        logger.error(f"Solana RPC error: {e}")
        return {}

def get_helius_token_info(mint: str) -> dict:
    """Rich token data from Helius DAS."""
    try:
        r = requests.post(
            HELIUS_RPC,
            json={"jsonrpc":"2.0","id":1,"method":"getAsset","params":{"id": mint}},
            timeout=8
        )
        data = r.json().get("result",{})
        meta = data.get("content",{}).get("metadata",{})
        token_info = data.get("token_info",{})
        return {
            "name": meta.get("name",""),
            "symbol": meta.get("symbol",""),
            "supply": token_info.get("supply",0),
            "decimals": token_info.get("decimals",0),
            "price_usd": token_info.get("price_info",{}).get("price_per_token",0),
            "holders": token_info.get("price_info",{}),
        }
    except Exception as e:
        logger.error(f"Helius token info error: {e}")
        return {}

def build_full_context() -> str:
    """Build the richest possible free market context for AI."""
    lines = ["[LIVE MARKET INTELLIGENCE]"]

    # Global market
    gm = get_global_market()
    if gm:
        total = gm.get("total_mcap",0)
        chg = gm.get("market_cap_change_24h",0)
        btc_dom = gm.get("btc_dominance",0)
        sol_dom = gm.get("sol_dominance",0)
        lines.append(f"Global MCap: ${total/1e12:.2f}T ({chg:+.1f}% 24h) | BTC dom: {btc_dom:.1f}% | SOL dom: {sol_dom:.2f}%")

    # SOL ecosystem prices
    prices = get_sol_prices()
    if prices:
        def fmt(coin_id, sym):
            d = prices.get(coin_id, {})
            p = d.get("usd", 0)
            c = d.get("usd_24h_change", 0)
            return f"{sym}: ${p:,.4f} {c:+.1f}%"
        lines.append(fmt("solana","SOL") + " | " + fmt("bitcoin","BTC").replace("$","$") + " | " + fmt("ethereum","ETH"))
        defi = []
        for cid, sym in [("jup-governance-token","JUP"),("raydium","RAY"),("orca","ORCA"),("jito-governance-token","JITO"),("bonk","BONK")]:
            d = prices.get(cid,{})
            if d.get("usd"):
                defi.append(f"{sym} {d.get('usd_24h_change',0):+.1f}%")
        if defi:
            lines.append(f"Solana DeFi: {' | '.join(defi)}")

    # Solana TPS
    net = get_solana_network_stats()
    if net.get("tps"):
        lines.append(f"Solana TPS: {net['tps']:,.0f}")

    # CoinGecko trending
    trending = get_coingecko_trending()
    if trending:
        tr_str = ", ".join(f"{t['symbol']}({t['change_24h']:+.0f}%)" for t in trending[:6])
        lines.append(f"CG Trending: {tr_str}")

    # DexScreener trending
    dex = get_dex_trending()
    if dex:
        lines.append("🔥 Trending on Solana (DexScreener):")
        for t in dex[:5]:
            lines.append(f"  {t['symbol']}: ${t['price']} {t['change_24h']:+.1f}% | Vol ${t['volume_24h']:,.0f} | MCap ${t['mcap']:,.0f}")

    # New pairs
    new_pairs = get_new_solana_pairs()
    if new_pairs:
        lines.append("🆕 Fresh Solana launches:")
        for p in new_pairs[:4]:
            lines.append(f"  {p['symbol']}: ${p['price']} {p['change_24h']:+.1f}% | {p['age_hours']}h old | Vol ${p['volume_24h']:,.0f}")

    # Boosted tokens
    boosted = get_dex_boosted()
    if boosted:
        syms = [b['symbol'] for b in boosted if b['symbol']]
        if syms:
            lines.append(f"💊 Boosted (paid promo): {', '.join(syms[:4])}")

    # Magic Eden NFTs
    me = get_magic_eden_trending()
    if me:
        lines.append("🖼 Top Solana NFTs (Magic Eden):")
        for c in me[:3]:
            lines.append(f"  {c['name']}: floor {c['floor']:.2f} SOL")

    lines.append("[END INTEL]")
    return "\n".join(lines)

if __name__ == "__main__":
    print(build_full_context())
