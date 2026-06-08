"""
whale_tracker.py — watches for smart money moves on Solana
Writes whale_alert memories to brain so consensus can vote on them
"""
import requests, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

INTERVAL = 60  # check every 60s
CY='\033[96m'; GR='\033[92m'; RS='\033[0m'; BD='\033[1m'

# Known smart wallet addresses (add more as you find them)
SMART_WALLETS = [
    "GVXRSBjFk6e6J3NbVPXohDJetcTjaeeuykUpbQF68Eq",  # known profitable trader
    "5tzFkiKscXHK5ZXCGbGuPuggf6B5uG3DMFN9Z9UXQXRH",  # another whale
]

def get(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def check_wallet_trades(wallet):
    """Get recent trades from a smart wallet via DexScreener"""
    data = get(f"https://api.dexscreener.com/latest/dex/search?q={wallet}")
    if not data:
        return []
    trades = []
    for pair in (data.get("pairs") or [])[:5]:
        name = pair.get("baseToken", {}).get("symbol", "?")
        mint = pair.get("baseToken", {}).get("address", "")
        vol  = float(pair.get("volume", {}).get("h1", 0) or 0)
        if vol > 5000:
            trades.append({"name": name, "mint": mint, "vol": vol})
    return trades

def scan_trending_for_whales():
    """Look at trending coins and flag ones with whale-level volume"""
    data = get("https://api.dexscreener.com/token-boosts/latest/v1")
    if not data:
        return
    for token in (data if isinstance(data, list) else [])[:20]:
        mint = token.get("tokenAddress", "")
        if not mint:
            continue
        pair_data = get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        if not pair_data:
            continue
        pairs = pair_data.get("pairs") or []
        if not pairs:
            continue
        p = pairs[0]
        name   = p.get("baseToken", {}).get("symbol", "?")
        vol1h  = float(p.get("volume", {}).get("h1", 0) or 0)
        buys   = int(p.get("txns", {}).get("h1", {}).get("buys", 0) or 0)
        mcap   = float(p.get("marketCap", 0) or 0)

        # Whale signal: huge volume relative to mcap in short time
        if mcap > 0 and vol1h / max(mcap, 1) > 5 and buys > 500:
            msg = f"{name} ({mint[:8]}) whale vol={vol1h:,.0f} buys={buys}"
            brain.learn("whale_tracker", "whale_alert", msg)
            print(f"  🐋 whale alert: {msg}")

def run():
    print(f"{CY}{BD}🐋 WHALE TRACKER — watching smart money{RS}")
    print(f"   Interval: {INTERVAL}s  |  Press Ctrl+C to stop\n")
    while True:
        try:
            scan_trending_for_whales()
        except Exception as e:
            print(f"  [whale] error: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()

HELIUS_API_KEY = "your-key-here"
HELIUS_URL = "https://api.helius.xyz/v0"

def get_helius_transactions(wallet, limit=10):
    url = f"{HELIUS_URL}/addresses/{wallet}/transactions"
    params = {"api-key": HELIUS_API_KEY, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[whale_tracker] Helius error for {wallet}: {e}")
        return []
