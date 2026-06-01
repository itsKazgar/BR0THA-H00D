"""
WHALE TRACKER AGENT
────────────────────
Monitors known smart/whale wallets for recent token buys.
If a whale bought something in the last hour → posts alert to brain.
Free APIs only: Solscan public + DexScreener.
"""
import sys, os, time, requests
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

INTERVAL = 60  # seconds between whale checks

# ── Known wallets to track ─────────────────────────────────
# Format: address -> label
WHALE_WALLETS = {
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "SOL Whale A",
    "5tzFkiKscXHK5ZXCGbCtEDFATCCrNPCa9x4rMcTFp5oF": "Degen Alpha",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh": "Pump Sniper",
    "ASTyfSima4LLAdDgoFGkgqoKowG1LZFDr9fAQrg7iaJZ": "Raydium Whale",
    "GUfCR9mK6azb9vcpsxgXyj7XRPAaYvkgMBMhpBrYFYqV": "MEV Bot Alpha",
}

seen_txs = set()

def get(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def fetch_wallet_tokens(address: str) -> list:
    """Get tokens held by a wallet via Solscan public API."""
    data = get(f"https://api.solscan.io/v2/account/tokens?address={address}&limit=20")
    if not data:
        return []
    return data.get("data", [])

def fetch_recent_transfers(address: str) -> list:
    """Get recent token transfers for a wallet."""
    data = get(f"https://api.solscan.io/v2/account/token/txs?address={address}&limit=10")
    if not data:
        return []
    return data.get("data", [])

def get_token_info(mint: str) -> dict:
    """Get price/volume from DexScreener for a mint."""
    data = get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    if not data:
        return {}
    pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"]
    if not pairs:
        return {}
    best = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
    return {
        "name":     best.get("baseToken", {}).get("symbol", "?"),
        "price":    float(best.get("priceUsd", 0) or 0),
        "liq":      float(best.get("liquidity", {}).get("usd", 0) or 0),
        "vol_24h":  float(best.get("volume", {}).get("h24", 0) or 0),
        "change_1h":float(best.get("priceChange", {}).get("h1", 0) or 0),
        "url":      best.get("url", ""),
    }

def check_whales():
    now = datetime.now().strftime("%H:%M:%S")
    alerts = []

    for address, label in WHALE_WALLETS.items():
        try:
            txs = fetch_recent_transfers(address)
            for tx in txs:
                tx_id   = tx.get("txHash", "") or tx.get("signature", "")
                mint    = tx.get("tokenAddress", "") or tx.get("mint", "")
                change  = float(tx.get("changeAmount", 0) or 0)
                tx_type = tx.get("type", "")

                if not mint or not tx_id or tx_id in seen_txs:
                    continue
                seen_txs.add(tx_id)

                # Only care about incoming tokens (buys)
                if change <= 0 and "buy" not in tx_type.lower():
                    continue

                info = get_token_info(mint)
                if not info or info.get("liq", 0) < 10_000:
                    continue

                name = info.get("name", mint[:8])
                alerts.append({
                    "label":  label,
                    "name":   name,
                    "mint":   mint,
                    "price":  info.get("price", 0),
                    "liq":    info.get("liq", 0),
                    "vol":    info.get("vol_24h", 0),
                    "ch1h":   info.get("change_1h", 0),
                    "url":    info.get("url", ""),
                    "amount": abs(change),
                })
        except Exception as e:
            continue

    if alerts:
        print(f"\n[{now}] 🐋 WHALE TRACKER — {len(alerts)} new move(s):")
        for a in alerts:
            print(f"  🐋 {a['label']} bought {a['name']}")
            print(f"     price=${a['price']:.8f}  liq=${a['liq']:,.0f}  "
                  f"vol=${a['vol']:,.0f}  1h={a['ch1h']:+.1f}%")
            if a['url']:
                print(f"     🔗 {a['url']}")

            brain.remember("whale_tracker",
                f"WHALE {a['label']} bought {a['name']} @ ${a['price']:.8f} | "
                f"liq=${a['liq']:,.0f} vol=${a['vol']:,.0f} 1h={a['ch1h']:+.1f}%",
                type="whale_alert", tags=f"{a['name'].lower()},whale")

            # If whale buy + decent liquidity → boost as trade signal
            if a["liq"] > 50_000 and a["vol"] > 30_000:
                brain.remember("whale_tracker",
                    f"BUY {a['name']} @ ${a['price']:.8f} | score=65 | "
                    f"mcap=0 | age=0h | 🐋 whale: {a['label']}",
                    type="trade_signal", tags=f"{a['name'].lower()},whale,buy")
                print(f"     ✅ Elevated to trade signal")
    else:
        print(f"[{now}] 🐋 whale tracker: no new moves")

def run():
    brain.init_db()
    print("🐋 WHALE TRACKER started — monitoring smart wallets")
    print(f"   Watching {len(WHALE_WALLETS)} wallets\n")
    while True:
        try:
            check_whales()
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\n[whale_tracker] stopped.")
            break
        except Exception as e:
            print(f"[whale_tracker] error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
