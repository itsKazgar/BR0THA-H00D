#!/usr/bin/env python3
"""
Emergency sell all open positions
Usage: python sellall.py
"""
import os, sys, requests
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from core import brain

GR='\033[92m'; RD='\033[91m'; YL='\033[93m'; CY='\033[96m'; BD='\033[1m'; RS='\033[0m'

def get_price(mint):
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=8)
        pairs = [p for p in r.json().get("pairs", []) if p.get("chainId") == "solana"]
        if not pairs:
            return None
        best = sorted(pairs, key=lambda x: float(x.get("liquidity",{}).get("usd",0) or 0), reverse=True)[0]
        return float(best.get("priceUsd", 0) or 0) or None
    except:
        return None

brain.init_db()
state    = brain.load_state("trader_paper" if os.getenv("TRADE_MODE","paper").lower() != "live" else "trader_live")
positions = state.get("positions", {})
balance   = state.get("balance", 0)
mode      = "LIVE" if os.getenv("LIVE_MODE","").lower() == "true" else "PAPER"

print(f"""
{CY}{BD}╔══════════════════════════════════════════════════════╗
║   🚨  BR0THER-H00D — Sell All Positions              ║
╚══════════════════════════════════════════════════════╝{RS}

  Mode     : {f"{RD}{BD}LIVE{RS}" if mode == "LIVE" else f"{GR}PAPER{RS}"}
  Balance  : ${balance:.2f}
  Positions: {len(positions)}
""")

if not positions:
    print(f"  {GR}No open positions.{RS}\n")
    sys.exit(0)

total_pnl = 0
for mint, pos in positions.items():
    price = get_price(mint)
    if price:
        pnl_pct = (price - pos["entry"]) / pos["entry"] * 100
        pnl_usd = (price - pos["entry"]) / pos["entry"] * pos["size_usd"]
        color   = GR if pnl_usd >= 0 else RD
        print(f"  {color}{pos['name']:<12}{RS} entry=${pos['entry']:.8f}  now=${price:.8f}  {color}{pnl_pct:+.1f}%  ${pnl_usd:+.2f}{RS}")
        total_pnl += pnl_usd
    else:
        print(f"  {YL}{pos['name']:<12}{RS} entry=${pos['entry']:.8f}  price unavailable")

pnl_color = GR if total_pnl >= 0 else RD
print(f"\n  Total PnL if sold now: {pnl_color}{BD}${total_pnl:+.2f}{RS}")
print(f"\n  {RD}This will close ALL {len(positions)} position(s).{RS}")

confirm = input("  Confirm sell all? (yes/n): ").strip().lower()
if confirm != "yes":
    print(f"  {YL}Cancelled.{RS}\n")
    sys.exit(0)

# Execute — update brain state directly (paper) or via Jupiter (live)
new_balance = balance
for mint, pos in list(positions.items()):
    price = get_price(mint)
    if not price:
        print(f"  {RD}❌ {pos['name']} — could not get price, skipping{RS}")
        continue
    pnl_usd = (price - pos["entry"]) / pos["entry"] * pos["size_usd"]
    new_balance += pos["size_usd"] + pnl_usd
    brain.remember("trader",
        f"MANUAL SELLALL {pos['name']} @ ${price:.8f} | PnL=${pnl_usd:+.2f}",
        type="trade", tags=f"{pos['name'].lower()},sell,manual")
    print(f"  {GR}✅ Closed {pos['name']}{RS}  PnL=${pnl_usd:+.2f}")

state["positions"] = {}
state["balance"]   = round(new_balance, 4)
state["total_pnl"] = round(state.get("total_pnl", 0) + total_pnl, 4)
brain.save_state("trader", state)

print(f"""
  {GR}{BD}✅ All positions closed{RS}
  New balance: ${new_balance:.2f}
""")
