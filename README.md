# 🔺 BR0THER-H00D

A council of small AI agents ("brothers") that share one memory and
answer questions from real data. Each brother owns one job — crypto
prices, web search, tech news, tasks, weather — and an orchestrator
routes your request to whoever fits.

## What it does
- Pulls **real data** (CoinGecko, DexScreener, DuckDuckGo, Yahoo
  Finance, HackerNews) — summaries are grounded in retrieved results,
  not made up.
- Shares one SQLite "brain" so every brother can read what the others found.
- Organizes brothers into circles (Intel, Money, Ops) under an orchestrator.

## What it is NOT
- Not financial advice. The Money brothers **report** prices and news.
  They do not predict markets or tell you what to buy.
- Not autonomous. It drafts and reports; you decide and act.

## Setup
```bash
git clone <your-repo> && cd BR0THER-H00D
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your free Groq key
python3 smoke_test.py  # confirm everything's healthy
```

## Required
- `GROQ_API_KEY` — free at console.groq.com. Everything else is optional.

## Health check
```bash
python3 smoke_test.py
```

## Adding a brother
Drop a `.py` file in `brothers/` with `NAME`, `DESCRIPTION`, and a
`run(user_input)` function that returns a string (or `None` to pass).
It auto-loads. Run the smoke test to confirm.
