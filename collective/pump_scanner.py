
import requests
import time

PUMPPORTAL_URL = "https://pumpportal.fun/api/data/tokens/new"

def get_new_pump_tokens(limit=20):
    """Fetch newest pump.fun token launches - free, no key needed."""
    try:
        r = requests.get(PUMPPORTAL_URL, timeout=15)
        if r.status_code != 200:
            return []
        tokens = r.json()
        results = []
        for t in tokens[:limit]:
            results.append({
                "token": t.get("symbol", "UNKNOWN"),
                "name": t.get("name", ""),
                "mint": t.get("mint", ""),
                "market_cap": t.get("usd_market_cap", 0),
                "created_at": t.get("created_timestamp", 0),
                "description": t.get("description", "")[:100],
                "twitter": t.get("twitter", ""),
                "website": t.get("website", ""),
                "source": "pump.fun"
            })
        return results
    except Exception as e:
        return []

def get_graduated_tokens(limit=10):
    """Tokens that graduated from pump.fun to Raydium - these are the winners."""
    try:
        r = requests.get("https://pumpportal.fun/api/data/tokens/graduated", timeout=15)
        if r.status_code != 200:
            return []
        tokens = r.json()
        results = []
        for t in tokens[:limit]:
            results.append({
                "token": t.get("symbol", "UNKNOWN"),
                "mint": t.get("mint", ""),
                "market_cap": t.get("usd_market_cap", 0),
                "source": "pump.fun/graduated"
            })
        return results
    except Exception as e:
        return []

if __name__ == "__main__":
    print("NEW PUMP.FUN LAUNCHES:")
    tokens = get_new_pump_tokens(10)
    for t in tokens:
        print(f"  {t['token']} | mcap=${t['market_cap']:,.0f} | {t['name']}")
    print("")
    print("GRADUATED TOKENS:")
    grad = get_graduated_tokens(5)
    for t in grad:
        print(f"  {t['token']} | mcap=${t['market_cap']:,.0f}")
