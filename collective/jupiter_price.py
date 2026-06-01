
import requests

JUP_PRICE_URL = "https://api.jup.ag/price/v2"
JUP_TOKENS_URL = "https://tokens.jup.ag/tokens"
SOL_MINT = "So11111111111111111111111111111111111111112"

def get_jupiter_price(mint_address):
    """Get real Jupiter price for any token by mint address."""
    try:
        r = requests.get(
            JUP_PRICE_URL,
            params={"ids": mint_address, "vsToken": "USDC"},
            timeout=10
        )
        data = r.json()
        token_data = data.get("data", {}).get(mint_address, {})
        return {
            "mint": mint_address,
            "price_usd": token_data.get("price", 0),
            "source": "jupiter"
        }
    except Exception as e:
        return {"error": str(e)}

def get_top_tokens():
    """Get Jupiter verified token list."""
    try:
        r = requests.get(JUP_TOKENS_URL, timeout=15)
        tokens = r.json()
        return [{"symbol": t.get("symbol"), "mint": t.get("address"), "name": t.get("name")} for t in tokens[:50]]
    except Exception as e:
        return []

def get_sol_price():
    """Get current SOL price in USD."""
    try:
        r = requests.get(JUP_PRICE_URL, params={"ids": SOL_MINT}, timeout=10)
        data = r.json()
        price = data.get("data", {}).get(SOL_MINT, {}).get("price", 0)
        return float(price)
    except:
        return 0

if __name__ == "__main__":
    sol = get_sol_price()
    print(f"SOL price: ${sol}")
