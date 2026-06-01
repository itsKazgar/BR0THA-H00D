"""
news_scout.py — scans crypto sentiment and writes to brain
Writes sentiment memories so consensus can vote on market mood
"""
import requests, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

INTERVAL = 120  # check every 2 mins
CY='\033[96m'; GR='\033[92m'; RS='\033[0m'; BD='\033[1m'

BULLISH_WORDS = ["pump","moon","surge","breakout","bull","buy","gem","100x","launch","new"]
BEARISH_WORDS = ["dump","rug","crash","scam","sell","bear","dead","exit","warning","hack"]

def get(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def check_fear_greed():
    """Fear & greed index — below 30 is fear, above 70 is greed"""
    data = get("https://api.alternative.me/fng/?limit=1")
    if not data:
        return None
    val = int(data["data"][0]["value"])
    label = data["data"][0]["value_classification"]
    sentiment = "bullish" if val > 50 else "bearish"
    msg = f"fear_greed={val} ({label}) market={sentiment}"
    brain.learn("news_scout", "sentiment", msg)
    print(f"  📰 sentiment: {msg}")
    return val

def check_trending_sentiment():
    """Look at trending coins — if many are pumping, market is bullish"""
    data = get("https://api.dexscreener.com/token-boosts/latest/v1")
    if not data:
        return
    pumping = dumping = 0
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
        ch1h = float(pairs[0].get("priceChange", {}).get("h1", 0) or 0)
        if ch1h > 10:
            pumping += 1
        elif ch1h < -10:
            dumping += 1

    if pumping + dumping > 0:
        mood = "bullish" if pumping > dumping else "bearish"
        msg  = f"trending: {pumping} pumping vs {dumping} dumping — {mood}"
        brain.learn("news_scout", "sentiment", msg)
        print(f"  📰 {msg}")

def run():
    print(f"{CY}{BD}📰 NEWS SCOUT — scanning market sentiment{RS}")
    print(f"   Interval: {INTERVAL}s  |  Press Ctrl+C to stop\n")
    while True:
        try:
            check_fear_greed()
            check_trending_sentiment()
        except Exception as e:
            print(f"  [news] error: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
