<p align="center">
  <img src="assets/logo.png" alt="BR0THER-H00D" width="380">
</p>

<h1 align="center">BR0THER-H00D</h1>

<p align="center">
  <b>A council of AI agents that share one memory, run a Solana trading desk,
  and pay for their own tools on-chain.</b>
</p>

<p align="center">
  Built on Solana · Free to run · One shared brain · A real team
</p>

---

## The idea

Most "AI bots" are a single model in a loop. BR0THER-H00D is a **collective**:
many small specialist agents that share one SQLite memory, coordinate through a
Boss orchestrator, and each use the AI brain best suited to their job. The
scanner's find informs the analyst's call, which informs the risk manager's
veto, which informs the Boss's summary back to you. Less a script, more a desk
full of people who talk to each other.

<p align="center">
  <img src="assets/terminal.png" alt="BR0THER-H00D mode selection" width="820">
</p>

<p align="center"><sub>Mode selection on launch — the shared brain reports its
memory count and the eight agents stand ready.</sub></p>

---

## Core capabilities

### Shared brain
Every agent reads and writes one persistent SQLite memory, so knowledge
compounds across the team and across sessions. Nothing is siloed — what one
brother learns, the others can use.

### Auto-detecting AI brains
Add any AI key — Groq, OpenRouter, Anthropic, OpenAI, or local Hermes/Ollama —
and the system detects it automatically. Each brother can be assigned the best
brain for its job (`BRAIN_ANALYST=anthropic`, `BRAIN_SOCIAL=openrouter`),
falling back to a sensible default. One model call per task: adding more keys
buys better options and resilience, never multiplied cost. Runs fully on free
models if that is all you have. Inspect it with `python3 ai_status.py`.

### Solana trading desk
A complete, risk-first trading engine:

- **Multi-signal scanner** across DexScreener trends, scored by momentum,
  dip-buy, and breakout theses, sharpened by GeckoTerminal candle confirmation
  (real OHLCV structure, not a single percentage).
- **Tiered exits that secure profit:** partial take-profit at +15% and +30%,
  the stop ratchets to breakeven once the first tier banks, a profit floor
  holds gains, and the remainder trails — winners run, gains do not evaporate.
- **Hard risk controls:** position sizing, max open positions, a reserve rule,
  post-loss cooldowns, and a daily-loss kill switch that halts new entries.
- **Dual-source rug screen before every live buy:** RugCheck and GoPlus, plus a
  Jupiter honeypot sell-route test that quotes a buy and a sell — if a token
  cannot be sold, it is never bought. Any single source flagging danger rejects
  the trade; all checks fail safe if a service is unreachable.
- **Verified execution:** swaps confirm on-chain instead of firing and
  forgetting, with dynamic priority fees so trades actually land.

The trading core runs on rules alone. With no AI keys at all, it still trades;
adding brains makes it smarter, never fragile.

### Assistant mode — your AI team
A conversational Boss you talk to in plain language. It remembers the
conversation, knows its whole team, and delegates. Built-in tools: web search
and scraping, email (single and bulk), SMS, document and invoice generation,
social posts, expense tracking, habits, journaling, and a URL watcher.

Hire your own assistants, each with a name, a role, isolated memory, a granted
toolset, and standing recurring tasks:

```bash
python3 manage_team.py hire "Maya" "bookkeeper: tracks expenses, sends P&L"
python3 manage_team.py tools Maya log_expense get_expenses generate_invoice
python3 manage_team.py task Maya weekly:fri "email me a P&L summary"
```

### On-chain agent payments (x402 + Solana Pay)
Agents pay for on-chain digital services — APIs, compute, data, other agents'
tools — from one shared company wallet in USDC, settled on Solana for fractions
of a cent. Safety is built in: per-transaction cap, daily cap, allowlist, and
an approval queue for anything over the auto-limit. Off by default; every
payment is logged for a full audit trail.

```
pay status                  wallet, caps, spending today
pay x402 <url>              buy an x402 digital service autonomously
pay send <address> <usdc>   pay a Solana address or freelancer
pay pending / approve <id>  review and approve larger payments
```

---

## The five modes

| Mode | What it does |
|------|--------------|
| **1 · Solo Paper Trade** | The trader alone, simulated money — watch the engine work with zero risk |
| **2 · Paper + Agents** | The trader plus all eight brothers feeding it signals, still simulated |
| **3 · Live Trading** | The full team with real funds, behind the complete safety screen |
| **4 · Custom Mode** | Build and edit your own agent lineup |
| **5 · Assistant Mode** | The conversational Boss, your hireable team, and on-chain payments |

---

## Architecture

```
You ──► The Boss (orchestrator) ──► delegates to:
         │  remembers your chat,        ├─ Scanner    finds plays
         │  knows the whole team        ├─ Analyst    scores (with AI)
         │                              ├─ Risk Mgr   vetoes bad risk
         │                              ├─ Whale / News / Pump  intel
         │                              ├─ Trader     executes, safely
         │                              └─ Your custom assistants
         │
         ├─ Safety Brother  RugCheck + GoPlus + honeypot test before buys
         ├─ Enrich Brother  GeckoTerminal candles confirm momentum
         ├─ AI Router       best brain per brother, auto-detected
         └─ Payments        x402 + Solana Pay, capped and approval-gated
```

---

## Data sources

Free, no key required: DexScreener, Jupiter, GeckoTerminal, RugCheck, GoPlus,
CoinGecko, Solana RPC. Add an optional Helius key for faster RPC and priority
fees.

---

## Quickstart

```bash
git clone https://github.com/itsKazgar/BR0THER-H00D && cd BR0THER-H00D
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add a free Groq key (console.groq.com) to start
python3 setup.py              # optional guided AI setup wizard
python3 smoke_test.py         # should report: all systems healthy
python3 Start.py              # launch and pick a mode
```

Useful checks:

```bash
python3 ai_status.py                     # detected AI brains and assignments
python3 safety_brother.py <token_mint>   # run the rug screen on a token
python3 manage_team.py list              # your assistant team
```

---

## Built honestly

- **Not financial advice.** The trading agents apply rules and risk controls;
  they do not predict markets. Memecoin trading can lose everything you deploy.
  Paper-trade first, use a dedicated wallet, start small.
- **Safety is the product.** Every consequential action — a live trade, a
  payment, a bulk email — is capped, screened, or queued for approval.
- **Your keys stay yours.** Private keys live only in your local `.env`, never
  in the database, never in logs, never committed.

---

## License

MIT — see [LICENSE](LICENSE).

<p align="center"><sub>Built by <a href="https://github.com/itsKazgar">@itsKazgar</a> · Solana · 2026</sub></p>
