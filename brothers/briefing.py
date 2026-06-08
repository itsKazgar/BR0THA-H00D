import os, sys, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain
from datetime import datetime

NAME        = "Briefing Brother"
DESCRIPTION = "Daily morning briefing — prices, market, positions, todos"
ENABLED     = True
COMMANDS    = ["briefing", "morning", "gm", "daily", "summary"]

def run(user_input):
    lower = user_input.lower().strip()
    if lower not in ["briefing", "morning", "gm", "daily", "summary", "good morning", "morning briefing"]:
        return None

    lines = [f"🌅 MORNING BRIEFING — {datetime.now().strftime('%A %B %d, %Y %H:%M')}",
             "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]

    # SOL price
    try:
        r   = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana,bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true", timeout=6)
        d   = r.json()
        sol = d.get("solana", {})
        btc = d.get("bitcoin", {})
        eth = d.get("ethereum", {})
        lines.append(f"\n💰 PRICES")
        lines.append(f"  ◎ SOL: ${sol.get('usd',0):,.2f}  {sol.get('usd_24h_change',0):+.1f}%")
        lines.append(f"  ₿ BTC: ${btc.get('usd',0):,.0f}  {btc.get('usd_24h_change',0):+.1f}%")
        lines.append(f"  Ξ ETH: ${eth.get('usd',0):,.0f}  {eth.get('usd_24h_change',0):+.1f}%")
    except:
        lines.append("  Could not fetch prices.")

    # Fear & greed
    try:
        r  = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        d  = r.json()["data"][0]
        fg = int(d["value"])
        emoji = "😱" if fg < 25 else "😨" if fg < 45 else "😐" if fg < 55 else "😏" if fg < 75 else "🤑"
        lines.append(f"\n{emoji} MARKET MOOD")
        lines.append(f"  Fear & Greed: {fg} ({d['value_classification']})")
    except:
        pass

    # Portfolio
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
        mode = os.getenv("TRADE_MODE", "paper").lower()
        s    = brain.load_state(f"trader_{mode}")
        if s:
            bal  = s.get("balance", 0)
            pnl  = s.get("total_pnl", 0)
            pos  = s.get("positions", {})
            hist = s.get("history", [])
            wins = sum(1 for t in hist if t.get("pnl_pct", 0) > 0)
            wr   = f"{wins/len(hist)*100:.0f}%" if hist else "n/a"
            lines.append(f"\n📊 TRADER ({mode.upper()})")
            lines.append(f"  Balance: ${bal:.2f}  PnL: ${pnl:+.2f}  WR: {wr}")
            if pos:
                lines.append(f"  Open: {', '.join(p['name'] for p in pos.values())}")
            else:
                lines.append(f"  No open positions.")
    except:
        pass

    # Todos
    try:
        todos = brain.recall(type="todo", limit=5)
        if todos:
            lines.append(f"\n📋 YOUR TODOS")
            for t in todos[:5]:
                lines.append(f"  • {t['content'].replace('TODO: ', '')}")
    except:
        pass

    # Trending from scanner
    try:
        signals = brain.recall(type="trade_signal", limit=5)
        if signals:
            lines.append(f"\n🔥 LATEST SIGNALS")
            for s in signals[:3]:
                lines.append(f"  • {s['content'][:70]}")
    except:
        pass

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("Type 'portfolio' for full details | 'todos' for tasks")
    return "\n".join(lines)
