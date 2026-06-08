import os, requests, sys
from dotenv import load_dotenv
load_dotenv()

WALLET = os.getenv("WALLET_ADDRESS")
RPC = "https://api.mainnet-beta.solana.com"

# Real SOL balance
r = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[WALLET]})
sol = r.json()["result"]["value"] / 1e9
price_r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=5)
sol_price = float(price_r.json()["solana"]["usd"])
print(f"\n💰 REAL WALLET: {WALLET}")
print(f"   SOL: {sol:.4f} (${sol * sol_price:.2f})")

# All tokens
r2 = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":"getTokenAccountsByOwner","params":[WALLET,{"programId":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},{"encoding":"jsonParsed"}]})
tokens = r2.json()["result"]["value"]
if tokens:
    print(f"\n🪙 TOKENS:")
    for t in tokens:
        info = t["account"]["data"]["parsed"]["info"]
        amt = info["tokenAmount"]["uiAmount"]
        if amt and float(amt) > 0:
            print(f"   Mint: {info['mint']}  Amount: {amt}")
else:
    print("   No tokens found")
