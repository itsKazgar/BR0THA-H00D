import requests, sys, os, threading, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, personality
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Stocks Brother"
DESCRIPTION = "Live stock prices via Yahoo Finance — free, no key needed"
ENABLED     = True
COMMANDS    = ["stock <ticker>", "price AAPL", "stocks TSLA NVDA"]

TRIGGERS    = ["stock ", "stocks ", "share ", "ticker ",
               "nasdaq", "sp500", "dow ", "nyse "]

HEADERS = {"User-Agent": "Mozilla/5.0"}

def _price(ticker: str) -> dict:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}?interval=1d&range=1d"
        r   = requests.get(url, headers=HEADERS, timeout=8)
        d   = r.json()
        meta = d["chart"]["result"][0]["meta"]
        price  = meta.get("regularMarketPrice", 0)
        prev   = meta.get("chartPreviousClose", price)
        change = ((price - prev) / prev * 100) if prev else 0
        name   = meta.get("shortName", ticker)
        return {"ticker": ticker.upper(), "name": name,
                "price": price, "change": change}
    except Exception as e:
        return {"error": str(e)}

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    # Extract tickers — words in uppercase or after trigger word
    words  = user_input.upper().split()
    skip   = {"STOCK", "STOCKS", "SHARE", "PRICE", "TICKER"}
    tickers = [w for w in words if w.isalpha() and w not in skip and len(w) <= 5]

    if not tickers:
        return "Give me a ticker — e.g. 'stock AAPL' or 'stocks TSLA NVDA'"

    lines  = ["📈 STOCKS\n"]
    for t in tickers[:5]:
        d = _price(t)
        if "error" in d:
            lines.append(f"  ❌ {t}: could not fetch")
        else:
            arrow = "🟢" if d["change"] >= 0 else "🔴"
            lines.append(f"  {arrow} {d['ticker']} ({d['name']}): ${d['price']:,.2f}  {d['change']:+.2f}%")

    result = "\n".join(lines)
    threading.Thread(target=personality.evolve,
        args=("stocks", f"fetched stocks {tickers}"), daemon=True).start()
    return result
