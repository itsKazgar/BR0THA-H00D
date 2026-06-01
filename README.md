# BR0THER-H00D — Solana Alpha Collective

A 7-agent AI trading system for Solana memecoins.

Scans, scores, reasons, and trades — paper or live.

## Quick Start (30 seconds)

    git clone https://github.com/itsKazgar/BR0THER-H00D
    cd BR0THER-H00D
    bash install.sh
    python start.py

No keys needed. Works immediately.

## Tiers

### Tier 0 — Zero Config
Works out of the box. No keys, no setup.
- Scans DexScreener, pump.fun, CoinGecko every 45s
- Rule-based AI scoring
- Paper trades with $100 virtual balance
- 7 agents running automatically

### Tier 1 — Smarter AI
Add free keys to .env:
- GROQ_API_KEY — console.groq.com — Llama 3 reasoning
- OPENROUTER_API_KEY — openrouter.ai — Claude, Gemini, DeepSeek, Grok
- TELEGRAM_BOT_TOKEN — @BotFather — phone alerts for every trade

### Tier 2 — Live Trading
Add to .env:
    LIVE_MODE=true
    WALLET_PRIVATE_KEY=your_base58_key_here

Export private key from Phantom: Settings > Security > Export Private Key
WARNING: Start with small amounts. Experimental software.

## Local AI (Hermes — free, private, no API key)
Requires 8GB+ RAM:
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull nous-hermes-2-mistral-7b
    ollama serve &
    python start.py

Auto-detects Hermes. No config needed.

## Agents
- Scanner      — hunts trending tokens across all sources
- Whale Tracker — watches smart wallet moves
- News Scout   — scans crypto news and sentiment
- Pump Hunter  — finds early pump.fun gems
- Risk Manager — monitors portfolio and enforces limits
- Analyst      — AI reasoning on every signal
- Trader       — executes paper or live trades
- Memory Keeper — logs learnings every 5 min

## Settings (agents/trading/trader.py)
    MIN_SCORE       = 80     # minimum score to consider trading
    MAX_TRADE_PCT   = 0.04   # 4% of balance per trade
    STOP_LOSS_PCT   = 0.10   # stop loss at -10%
    MAX_HOLD_MINS   = 120    # force exit after 120 mins
    # Exits are tiered — T1 +12% (sell 33%), T2 +25% (sell 33%), T3 trails freely

## Security
- Never share or commit your .env file
- Always test in paper mode first (LIVE_MODE=false)
- Start live trading with small amounts ($10-20)

## License
MIT — use it, fork it, improve it.

## Dashboard

A terminal-style web dashboard for monitoring your agents live.

**Start the API:**

    uvicorn brotha_api:app --host 0.0.0.0 --port 8000

**Then open in your browser:**

    http://localhost:8000

Shows live agent status, trade history, balance, signals, and market data.
Run alongside `python Start.py` for full live view.
