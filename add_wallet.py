#!/usr/bin/env python3
"""
Quick wallet setup for BR0THER-H00D
"""
import os, sys
from dotenv import set_key, load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

GR='\033[92m'; RD='\033[91m'; YL='\033[93m'; CY='\033[96m'; BD='\033[1m'; RS='\033[0m'

def main():
    print(f"""
{CY}{BD}╔══════════════════════════════════════════════════════╗
║   💳  BR0THER-H00D — Wallet Setup                    ║
╚══════════════════════════════════════════════════════╝{RS}

  This adds your Solana wallet for {RD}{BD}LIVE trading{RS}.
  Paper mode works without this — no wallet needed.

  {YL}How to export from Phantom:{RS}
    1. Open Phantom wallet
    2. Click the menu (top left)
    3. Settings → Security & Privacy
    4. Export Private Key
    5. Paste it below

  {RD}{BD}⚠️  NEVER share this key with anyone else.{RS}
  {RD}   It gives full access to your wallet.{RS}
""")

    current = os.getenv("WALLET_PRIVATE_KEY", "")
    if current and current != "your_base58_key_here":
        print(f"  {GR}✅ Wallet already configured{RS} (key starts with: {current[:6]}...)")
        overwrite = input("  Overwrite with a new key? (y/n): ").strip().lower()
        if overwrite != "y":
            print("  Keeping existing wallet. Done!")
            return

    key = input("  Paste your private key here: ").strip()

    if not key:
        print(f"  {YL}No key entered. Exiting.{RS}")
        return

    if len(key) < 40:
        print(f"  {RD}❌ That doesn't look like a valid key (too short).{RS}")
        print(f"     Make sure you copied the full base58 private key.")
        return

    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w").close()

    set_key(ENV_PATH, "WALLET_PRIVATE_KEY", key)
    print(f"\n  {GR}✅ Wallet key saved to .env{RS}")

    print(f"\n  {YL}Enable live trading now?{RS}")
    print(f"  ({RD}real money{RS} — start with $10-20 max)")
    live = input("  Enable LIVE_MODE? (y/n): ").strip().lower()

    if live == "y":
        set_key(ENV_PATH, "LIVE_MODE", "true")
        print(f"\n  {RD}{BD}⚠️  LIVE MODE ENABLED{RS}")
        print(f"  The bot will execute real trades on Solana.")
        print(f"  Make sure your wallet has some SOL for gas fees.")
    else:
        set_key(ENV_PATH, "LIVE_MODE", "false")
        print(f"\n  {GR}Paper mode kept (LIVE_MODE=false){RS}")
        print(f"  Your key is saved. Run this script again to enable live trading.")

    print(f"""
  {GR}{BD}All done!{RS}
  Run {BD}python start.py{RS} to start the bot.
""")

if __name__ == "__main__":
    main()
