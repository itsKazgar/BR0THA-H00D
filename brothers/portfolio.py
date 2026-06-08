import os, sys, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain

NAME        = "Portfolio Brother"
DESCRIPTION = "Shows positions, PnL, win rate, trade history"
ENABLED     = True
COMMANDS    = ["portfolio", "positions", "pnl", "stats", "trades"]

def _sol_price():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=6)
        return float(r.json()["solana"]["usd"])
    except:
        return 0

def run(user_input):
    lower = user_input.lower().strip()
    if lower not in ["portfolio", "positions", "pnl", "stats", "trades", "my portfolio", "my stats"]:
        return None

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    mode = os.getenv("TRADE_MODE", "paper").lower()
    key  = "trader_live" if mode == "live" else "trader_paper"
    s    = brain.load_state(key)
    if not s:
        return "No trading data found. Start the trader first."

    bal   = s.get("balance", 0)
    pnl   = s.get("total_pnl", 0)
    pos   = s.get("positions", {})
    hist  = s.get("history", [])
    sol_p = _sol_price()

    # Stats
    wins     = [t for t in hist if t.get("pnl_pct", 0) > 0]
    losses   = [t for t in hist if t.get("pnl_pct", 0) <= 0]
    wr       = f"{len(wins)/len(hist)*100:.0f}%" if hist else "n/a"
    avg_win  = sum(t["pnl_pct"] for t in wins)  / len(wins)  if wins   else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    best     = max(hist, key=lambda t: t["pnl_pct"]) if hist else None
    worst    = min(hist, key=lambda t: t["pnl_pct"]) if hist else None

    lines = [
        f"💼 PORTFOLIO ({mode.upper()} MODE)",
        f"",
        f"💰 Balance:  ${bal:.2f}" + (f"  (◎{bal/sol_p:.4f} SOL)" if sol_p else ""),
        f"📈 Total PnL: ${pnl:+.2f}",
        f"🎯 Win Rate:  {wr} ({len(wins)}W / {len(losses)}L from {len(hist)} trades)",
        f"📊 Avg Win:   +{avg_win:.1f}%  |  Avg Loss: {avg_loss:.1f}%",
    ]

    if best:
        lines.append(f"🏆 Best:  {best['name']} +{best['pnl_pct']:.1f}%")
    if worst:
        lines.append(f"💀 Worst: {worst['name']} {worst['pnl_pct']:.1f}%")

    if pos:
        lines.append(f"\n📂 Open Positions ({len(pos)}):")
        for mint, p in pos.items():
            try:
                r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=6)
                pairs = [x for x in r.json().get("pairs", []) if x.get("chainId") == "solana"]
                price = float(pairs[0].get("priceUsd", 0)) if pairs else p["entry"]
            except:
                price = p["entry"]
            pnl_pct = (price - p["entry"]) / p["entry"] * 100
            emoji   = "🟢" if pnl_pct >= 0 else "🔴"
            lines.append(f"  {emoji} {p['name']:<12} entry=${p['entry']:.8f} "
                        f"now=${price:.8f} {pnl_pct:+.1f}%")
    else:
        lines.append("\n📂 No open positions.")

    if hist:
        lines.append(f"\n🕐 Last 3 trades:")
        for t in hist[-3:]:
            e = "✅" if t["pnl_pct"] > 0 else "❌"
            lines.append(f"  {e} {t['name']:<12} {t['pnl_pct']:+.1f}%  {t.get('reason','')[:30]}")

    return "\n".join(lines)
