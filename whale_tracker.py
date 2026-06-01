
import requests
import os
from dotenv import load_dotenv
load_dotenv(override=True)

HELIUS_KEY = os.getenv("HELIUS_API_KEY", "")
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

# Known whale/smart money wallets to track
WHALE_WALLETS = [
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # known Solana whale
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",  # famous trader
]

def get_wallet_transactions(wallet_address, limit=10):
    """Get recent transactions for a wallet using Helius."""
    try:
        r = requests.post(
            HELIUS_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [wallet_address, {"limit": limit}]
            },
            timeout=15
        )
        data = r.json()
        return data.get("result", [])
    except Exception as e:
        return []

def get_wallet_balance(wallet_address):
    """Get SOL balance of a wallet."""
    try:
        r = requests.post(
            HELIUS_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [wallet_address]
            },
            timeout=10
        )
        data = r.json()
        lamports = data.get("result", {}).get("value", 0)
        return lamports / 1e9  # convert to SOL
    except:
        return 0

def get_token_holders(mint_address, limit=10):
    """Get top holders of a token using Helius."""
    try:
        url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"
        r = requests.post(url, json={
            "jsonrpc": "2.0",
            "id": "helius",
            "method": "getTokenLargestAccounts",
            "params": [mint_address]
        }, timeout=15)
        data = r.json()
        return data.get("result", {}).get("value", [])[:limit]
    except Exception as e:
        return []

def scan_whale_activity():
    """Check recent activity of known whale wallets."""
    activity = []
    for wallet in WHALE_WALLETS:
        txns = get_wallet_transactions(wallet, limit=5)
        bal = get_wallet_balance(wallet)
        activity.append({
            "wallet": wallet[:8] + "...",
            "sol_balance": round(bal, 2),
            "recent_txns": len(txns)
        })
    return activity

if __name__ == "__main__":
    print("WHALE ACTIVITY:")
    for w in scan_whale_activity():
        print(f"  {w['wallet']} | {w['sol_balance']} SOL | {w['recent_txns']} recent txns")
