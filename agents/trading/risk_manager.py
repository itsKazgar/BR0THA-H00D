CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'; BD='\033[1m'; DM='\033[2m'; RS='\033[0m'
import requests, time, sys, os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

INTERVAL       = 30
MAX_DRAWDOWN   = 0.15   # alert if portfolio down >15%
MAX_LOSS_ROW   = 3      # alert after 3 losses in a row
START_BALANCE  = 100.0

def get(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def check():
    now   = datetime.now().strftime("%H:%M:%S")
    state = brain.load_state("trader_paper" if os.getenv("TRADE_MODE","paper").lower() != "live" else "trader_live")
    if not state:
        return

    balance   = state.get("balance", START_BALANCE)
    positions = state.get("positions", {})
    history   = state.get("history", [])
    total_pnl = state.get("total_pnl", 0)
    alerts    = []

    # 1. Drawdown check
    drawdown = (START_BALANCE - balance) / START_BALANCE
    if drawdown > MAX_DRAWDOWN:
        alerts.append(f"⚠️  DRAWDOWN ALERT: portfolio down {drawdown:.0%} (${balance:.2f})")

    # 2. Consecutive losses
    if len(history) >= MAX_LOSS_ROW:
        last = history[-MAX_LOSS_ROW:]
        if all(t["pnl_pct"] < 0 for t in last):
            losses = [t["pnl_pct"] for t in last]
            alerts.append(f"⚠️  {MAX_LOSS_ROW} LOSSES IN A ROW: {', '.join(f'{l:.1f}%' for l in losses)}")

    # 3. Check each position for danger signs
    for mint, pos in positions.items():
        data = get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        if not data:
            continue
        pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"]
        if not pairs:
            alerts.append(f"⚠️  {pos['name']} — NO PAIRS FOUND (possible rug)")
            continue
        p     = sorted(pairs, key=lambda x: float(x.get("liquidity",{}).get("usd",0) or 0), reverse=True)[0]
        liq   = float(p.get("liquidity", {}).get("usd", 0) or 0)
        vol   = float(p.get("volume", {}).get("h24", 0) or 0)
        price = float(p.get("priceUsd", 0) or 0)

        if liq < 5_000:
            alerts.append(f"🚨 {pos['name']} LIQUIDITY CRITICAL: ${liq:,.0f} — possible rug")
        if price > 0:
            pnl = (price - pos["entry"]) / pos["entry"] * 100
            if pnl < -20:
                alerts.append(f"🔴 {pos['name']} DOWN {pnl:.1f}% — consider manual exit")

        time.sleep(0.3)

    # 4. Win rate check
    if len(history) >= 5:
        wins     = sum(1 for t in history if t["pnl_pct"] > 0)
        win_rate = wins / len(history)
        if win_rate < 0.30:
            alerts.append(f"⚠️  WIN RATE LOW: {win_rate:.0%} ({wins}/{len(history)}) — review strategy")

    if alerts:
        print(f"\n{RD}{BD}╔══════════════════════════════════════╗{RS}")
        print(f"{RD}{BD}║  🛡️  RISK MANAGER  {now}           ║{RS}")
        for a in alerts:
            print(f"  {RD}{a}{RS}")
            brain.remember("risk_manager", a,
                type="risk_alert",
                tags="risk,alert")
        print(f"{RD}{BD}╚══════════════════════════════════════╝{RS}\n")
    else:
        print(f"  [{now}] 🛡️  all clear — balance=${balance:.2f}  positions={len(positions)}  pnl=${total_pnl:+.2f}")

def run():
    brain.init_db()
    print(f"{RD}{BD}🛡️  RISK MANAGER{RS} — monitoring portfolio health")
    print(f"   Max drawdown: {MAX_DRAWDOWN:.0%}  |  Loss streak alert: {MAX_LOSS_ROW}")
    print(f"   Interval: {INTERVAL}s  |  Press Ctrl+C to stop\n")
    check()
    while True:
        try:
            time.sleep(INTERVAL)
            check()
        except KeyboardInterrupt:
            print("\n[risk_manager] stopped.")
            break
        except Exception as e:
            print(f"[risk_manager] error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
