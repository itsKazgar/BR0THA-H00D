import os, sys, requests, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain

NAME        = "Alert Brother"
DESCRIPTION = "Set price alerts — notifies you when price is hit"
ENABLED     = True
COMMANDS    = ["alert <symbol> <price>", "alerts", "clear alerts"]

_active_alerts = {}
_monitor_thread = None

def _sol_price():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=6)
        return float(r.json()["solana"]["usd"])
    except:
        return 0

def _token_price(symbol):
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/search?q={symbol}", timeout=8)
        pairs = [p for p in r.json().get("pairs", [])
                 if p.get("chainId") == "solana"
                 and p.get("baseToken", {}).get("symbol", "").upper() == symbol.upper()]
        if not pairs:
            return 0
        best = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
        return float(best.get("priceUsd", 0) or 0)
    except:
        return 0

def _monitor_loop():
    while True:
        try:
            triggered = []
            for key, alert in list(_active_alerts.items()):
                sym   = alert["symbol"]
                target = alert["target"]
                above  = alert["above"]
                price  = _sol_price() if sym == "SOL" else _token_price(sym)
                if price <= 0:
                    continue
                hit = (above and price >= target) or (not above and price <= target)
                if hit:
                    direction = "🚀 ABOVE" if above else "📉 BELOW"
                    msg = f"🔔 ALERT: {sym} is {direction} ${target:.4f} — now ${price:.4f}"
                    print(f"\n  {msg}\n")
                    brain.remember("assistant", msg, type="price_alert", tags=f"alert,{sym.lower()}")
                    triggered.append(key)
            for k in triggered:
                del _active_alerts[k]
        except:
            pass
        time.sleep(30)

def _ensure_monitor():
    global _monitor_thread
    if _monitor_thread is None or not _monitor_thread.is_alive():
        _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        _monitor_thread.start()

def run(user_input):
    lower = user_input.lower().strip()

    if lower in ["alerts", "my alerts", "show alerts"]:
        if not _active_alerts:
            return "No active alerts. Try: alert SOL 80"
        lines = ["🔔 Active alerts:"]
        for k, a in _active_alerts.items():
            direction = "above" if a["above"] else "below"
            lines.append(f"  • {a['symbol']} {direction} ${a['target']:.4f}")
        return "\n".join(lines)

    if lower in ["clear alerts", "delete alerts", "remove alerts"]:
        _active_alerts.clear()
        return "✅ All alerts cleared."

    if lower.startswith("alert "):
        parts = lower.replace("alert ", "").split()
        if len(parts) < 2:
            return "Usage: alert SOL 80  or  alert BONK 0.00005"
        try:
            symbol = parts[0].upper()
            target = float(parts[1])
            current = _sol_price() if symbol == "SOL" else _token_price(symbol)
            above   = current < target
            key     = f"{symbol}_{target}"
            _active_alerts[key] = {"symbol": symbol, "target": target, "above": above}
            _ensure_monitor()
            direction = "rises above" if above else "drops below"
            return (f"✅ Alert set: notify when {symbol} {direction} ${target:.4f}\n"
                   f"   Current price: ${current:.4f}")
        except Exception as e:
            return f"Usage: alert SOL 80\nError: {e}"

    return None
