#!/usr/bin/env python3
"""
Toggle between LIVE and PAPER trading mode
Usage: python toggle.py
"""
import os
from dotenv import set_key, load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

GR='\033[92m'; RD='\033[91m'; YL='\033[93m'; CY='\033[96m'; BD='\033[1m'; RS='\033[0m'

current = os.getenv("LIVE_MODE", "false").lower() == "true"
wallet  = os.getenv("WALLET_PRIVATE_KEY", "")

print(f"""
{CY}{BD}╔══════════════════════════════════════════════════════╗
║   🔄  BR0THER-H00D — Trading Mode Toggle             ║
╚══════════════════════════════════════════════════════╝{RS}

  Current mode : {f"{RD}{BD}LIVE{RS}" if current else f"{GR}PAPER{RS}"}
  Wallet       : {f"{GR}✅ set ({wallet[:6]}...){RS}" if wallet and wallet != "your_base58_key_here" else f"{RD}❌ not set — run: python add_wallet.py{RS}"}
""")

if current:
    print(f"  Currently {RD}{BD}LIVE{RS} — switch to paper?")
    choice = input("  Switch to PAPER mode? (y/n): ").strip().lower()
    if choice == "y":
        set_key(ENV_PATH, "LIVE_MODE", "false")
        print(f"\n  {GR}✅ Switched to PAPER mode — no real trades{RS}")
    else:
        print(f"  Staying in LIVE mode.")
else:
    print(f"  Currently {GR}PAPER{RS} — switch to live?")
    if not wallet or wallet == "your_base58_key_here":
        print(f"\n  {RD}❌ No wallet set. Run first:{RS}")
        print(f"     python add_wallet.py\n")
    else:
        choice = input(f"  Switch to {RD}{BD}LIVE mode{RS} (real money)? (y/n): ").strip().lower()
        if choice == "y":
            set_key(ENV_PATH, "LIVE_MODE", "true")
            print(f"\n  {RD}{BD}⚠️  LIVE MODE ON{RS}")
            print(f"  Real trades will execute. Start small ($10-20).")
        else:
            print(f"  Staying in paper mode.")

print()
