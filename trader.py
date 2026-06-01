"""
paper_trader.py - BR0THA Smart Exit Engine

Exit strategy — always come out green, never all-in:
  Tier 1: Sell 33% at +15%  (locked profit, guaranteed)
  Tier 2: Sell 33% at +30%  (more locked)
  Tier 3: Trail last 33% with 8% trailing stop (rides moonshots)

  Hard stop: -12% on full position (cut losers fast)
  Position size: 3% of portfolio max (never all-in)
  Cooldown: 24hr ban on re-entering a stopped-out token

Worst case: -12% on 3% = 0.36% total portfolio loss per trade
Best case:  last third rides indefinitely with trailing stop
"""

import sqlite3, requests, time, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv(override=True)

DB_PATH   = "data/agent.db"
PORTFOLIO = 1000.0   # starting paper USD

# ── Position sizing ────────────────────────────────────────────────────────────
MAX_TRADE = 0.03     # never more than 3% of portfolio per trade

# ── Exit tiers (each is a fraction of the original position) ──────────────────
TIER1_PCT    = 0.15  # +15%  → sell 33%
TIER2_PCT    = 0.30  # +30%  → sell another 33%
TIER3_TRAIL  = 0.08  # trail last 33% with 8% drop from peak

# ── Hard stop ─────────────────────────────────────────────────────────────────
HARD_STOP    = -0.12  # -12% full exit before any tier fires

# ── Cooldown ──────────────────────────────────────────────────────────────────
COOLDOWN_HRS = 24    # hours before re-entering a stopped-out token

DEX_URL  = "https://api.dexscreener.com/latest/dex/search/?q="
HEADERS  = {"User-Agent": "Mozilla/5.0"}


# ══════════════════════════════════════════════════════════════════════════════
#  DB SETUP
# ══════════════════════════════════════════════════════════════════════════════

def init_paper_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id         INTEGER PRIMARY KEY,
            cash_usd   REAL DEFAULT 1000.0,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            token            TEXT,
            mint             TEXT,
            entry_price      REAL,
            current_price    REAL,
            peak_price       REAL,          -- for trailing stop on tier 3
            size_usd         REAL,          -- original position size
            tier1_tokens     REAL DEFAULT 0,
            tier2_tokens     REAL DEFAULT 0,
            tier3_tokens     REAL DEFAULT 0,
            tier1_hit        INTEGER DEFAULT 0,   -- 0/1 flag
            tier2_hit        INTEGER DEFAULT 0,
            tp_price_t1      REAL,          -- +15%
            tp_price_t2      REAL,          -- +30%
            sl_price         REAL,          -- hard stop
            status           TEXT DEFAULT 'OPEN',
            pnl_usd          REAL DEFAULT 0,
            pnl_pct          REAL DEFAULT 0,
            agents_voted     INTEGER,
            confidence       REAL,
            opened_at        TEXT,
            closed_at        TEXT,
            close_reason     TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            token      TEXT,
            action     TEXT,
            price      REAL,
            size_usd   REAL,
            pnl_usd    REAL,
            pnl_pct    REAL,
            reason     TEXT,
            timestamp  TEXT
        );

        CREATE TABLE IF NOT EXISTS cooldown (
            token      TEXT PRIMARY KEY,
            expires_at TEXT
        );
        """)
        row = db.execute("SELECT * FROM portfolio WHERE id=1").fetchone()
        if not row:
            db.execute("INSERT INTO portfolio VALUES (1, ?, ?)",
                       (PORTFOLIO, datetime.utcnow().isoformat()))


# ══════════════════════════════════════════════════════════════════════════════
#  PORTFOLIO HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_portfolio():
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("SELECT cash_usd FROM portfolio WHERE id=1").fetchone()
        return row[0] if row else PORTFOLIO

def update_portfolio(cash):
    with sqlite3.connect(DB_PATH) as db:
        db.execute("UPDATE portfolio SET cash_usd=?, updated_at=? WHERE id=1",
                   (cash, datetime.utcnow().isoformat()))

def get_open_positions():
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("SELECT * FROM positions WHERE status='OPEN'").fetchall()
        cols = [d[0] for d in db.execute("SELECT * FROM positions LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

def get_current_price(token, mint=""):
    try:
        query = mint if mint and len(mint) > 20 else token
        r = requests.get(DEX_URL + query, headers=HEADERS, timeout=15)
        pairs = r.json().get("pairs", [])
        sol   = [p for p in pairs if p.get("chainId") == "solana"]
        p     = sol[0] if sol else (pairs[0] if pairs else None)
        if not p:
            return None
        return float(p.get("priceUsd") or 0)
    except:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  COOLDOWN
# ══════════════════════════════════════════════════════════════════════════════

def is_on_cooldown(token):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("SELECT expires_at FROM cooldown WHERE token=?", (token,)).fetchone()
        if not row:
            return False
        return datetime.utcnow().isoformat() < row[0]

def set_cooldown(token):
    expires = (datetime.utcnow() + timedelta(hours=COOLDOWN_HRS)).isoformat()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT OR REPLACE INTO cooldown VALUES (?, ?)", (token, expires))
    print(f"  [PAPER] 🚫 {token} on cooldown for {COOLDOWN_HRS}h (stopped out)")


# ══════════════════════════════════════════════════════════════════════════════
#  OPEN POSITION
# ══════════════════════════════════════════════════════════════════════════════

def open_position(token, mint, price, agents_voted, confidence):
    if is_on_cooldown(token):
        print(f"  [PAPER] ⏳ {token} is on cooldown — skip")
        return False

    cash     = get_portfolio()
    size_usd = round(cash * MAX_TRADE, 2)

    if size_usd < 5:
        print(f"  [PAPER] Not enough cash (${cash:.2f}) — skip")
        return False

    with sqlite3.connect(DB_PATH) as db:
        existing = db.execute(
            "SELECT id FROM positions WHERE token=? AND status='OPEN'", (token,)
        ).fetchone()
        if existing:
            print(f"  [PAPER] Already holding {token} — skip")
            return False

    price = float(price or 0)
    if price <= 0:
        print(f"  [PAPER] Invalid price for {token}")
        return False

    # Split into 3 equal buckets
    total_tokens = size_usd / price
    t1 = t2 = t3 = total_tokens / 3

    tp1  = price * (1 + TIER1_PCT)
    tp2  = price * (1 + TIER2_PCT)
    sl   = price * (1 + HARD_STOP)

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            INSERT INTO positions
            (token, mint, entry_price, current_price, peak_price,
             size_usd, tier1_tokens, tier2_tokens, tier3_tokens,
             tier1_hit, tier2_hit,
             tp_price_t1, tp_price_t2, sl_price,
             agents_voted, confidence, opened_at)
            VALUES (?,?,?,?,?,?,?,?,?,0,0,?,?,?,?,?,?)
        """, (token, mint, price, price, price,
              size_usd, t1, t2, t3,
              tp1, tp2, sl,
              agents_voted, confidence, datetime.utcnow().isoformat()))

        db.execute("""
            INSERT INTO trade_log (token, action, price, size_usd, pnl_usd, pnl_pct, reason, timestamp)
            VALUES (?,?,?,?,0,0,'OPEN',?)
        """, (token, "BUY", price, size_usd, datetime.utcnow().isoformat()))

    update_portfolio(cash - size_usd)

    print(f"  [PAPER] 🟢 BUY  {token} @ ${price:.8f}")
    print(f"          Size: ${size_usd:.2f} | 3 tiers of {total_tokens/3:.2f} tokens each")
    print(f"          T1: +15% @ ${tp1:.8f} | T2: +30% @ ${tp2:.8f} | T3: 8% trail")
    print(f"          Hard stop: -12% @ ${sl:.8f}")
    print(f"          Cash remaining: ${cash - size_usd:.2f}")
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  PARTIAL SELLS
# ══════════════════════════════════════════════════════════════════════════════

def _sell_tier(pos, tier_tokens, current_price, reason, label):
    entry      = pos["entry_price"]
    sell_value = tier_tokens * current_price
    cost_basis = tier_tokens * entry
    pnl_usd    = sell_value - cost_basis
    pnl_pct    = ((current_price - entry) / entry) * 100

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            INSERT INTO trade_log (token, action, price, size_usd, pnl_usd, pnl_pct, reason, timestamp)
            VALUES (?,?,?,?,?,?,?,?)
        """, (pos["token"], f"SELL-{label}", current_price, sell_value,
              pnl_usd, pnl_pct, reason, datetime.utcnow().isoformat()))

    cash = get_portfolio()
    update_portfolio(cash + sell_value)

    print(f"  [PAPER] 💰 {label} {pos['token']} @ ${current_price:.8f} ({pnl_pct:+.1f}%)")
    print(f"          Sold ${sell_value:.2f} | PnL on this slice: ${pnl_usd:+.2f} | Cash: ${cash + sell_value:.2f}")
    return pnl_usd


def _close_full(pos, current_price, reason):
    """Close all remaining tiers at once (hard stop or trail exit)."""
    entry = pos["entry_price"]
    # Sum whatever tokens are still open
    remaining = 0
    if not pos["tier1_hit"]:
        remaining += pos["tier1_tokens"]
    if not pos["tier2_hit"]:
        remaining += pos["tier2_tokens"]
    remaining += pos["tier3_tokens"]

    sell_value = remaining * current_price
    cost_basis = remaining * entry
    pnl_usd    = sell_value - cost_basis
    pnl_pct    = ((current_price - entry) / entry) * 100

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            UPDATE positions SET
                status='CLOSED', current_price=?, pnl_usd=?, pnl_pct=?,
                closed_at=?, close_reason=?
            WHERE id=?
        """, (current_price, pnl_usd, pnl_pct,
              datetime.utcnow().isoformat(), reason, pos["id"]))

        db.execute("""
            INSERT INTO trade_log (token, action, price, size_usd, pnl_usd, pnl_pct, reason, timestamp)
            VALUES (?,?,?,?,?,?,?,?)
        """, (pos["token"], "SELL-FULL", current_price, sell_value,
              pnl_usd, pnl_pct, reason, datetime.utcnow().isoformat()))

    cash = get_portfolio()
    update_portfolio(cash + sell_value)

    icon = "🔴" if pnl_usd < 0 else "✅"
    print(f"  [PAPER] {icon} CLOSE {pos['token']} [{reason}] @ ${current_price:.8f} ({pnl_pct:+.1f}%)")
    print(f"          Got back ${sell_value:.2f} | PnL: ${pnl_usd:+.2f} | Cash: ${cash + sell_value:.2f}")

    if reason == "SL":
        set_cooldown(pos["token"])

    return pnl_usd


# ══════════════════════════════════════════════════════════════════════════════
#  CHECK POSITIONS — call every 60s from loop.py
# ══════════════════════════════════════════════════════════════════════════════

def check_positions():
    positions = get_open_positions()
    if not positions:
        return

    print(f"  [PAPER] Checking {len(positions)} open position(s)...")
    total_pnl = 0

    for pos in positions:
        current = get_current_price(pos["token"], pos.get("mint", ""))
        if not current or current <= 0:
            print(f"  [PAPER] Can't price {pos['token']} — skipping")
            continue

        entry   = pos["entry_price"]
        pnl_pct = ((current - entry) / entry) * 100

        # Update current price + peak price in DB
        new_peak = max(pos["peak_price"] or entry, current)
        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                "UPDATE positions SET current_price=?, peak_price=?, pnl_pct=? WHERE id=?",
                (current, new_peak, pnl_pct, pos["id"])
            )
        pos["peak_price"]   = new_peak
        pos["current_price"] = current

        t1_hit = bool(pos["tier1_hit"])
        t2_hit = bool(pos["tier2_hit"])

        print(f"  [PAPER] {pos['token']:12} entry=${entry:.8f} now=${current:.8f} {pnl_pct:+.1f}%"
              f"  T1={'✅' if t1_hit else '○'} T2={'✅' if t2_hit else '○'}")

        # ── Hard stop (fires before any tier) ────────────────────────────────
        if current <= pos["sl_price"]:
            total_pnl += _close_full(pos, current, "SL")
            continue

        # ── Tier 1: sell 33% at +15% ─────────────────────────────────────────
        if not t1_hit and current >= pos["tp_price_t1"]:
            pnl = _sell_tier(pos, pos["tier1_tokens"], current, "T1 +15%", "T1")
            total_pnl += pnl
            with sqlite3.connect(DB_PATH) as db:
                db.execute("UPDATE positions SET tier1_hit=1 WHERE id=?", (pos["id"],))
            t1_hit = True

        # ── Tier 2: sell another 33% at +30% ─────────────────────────────────
        if t1_hit and not t2_hit and current >= pos["tp_price_t2"]:
            pnl = _sell_tier(pos, pos["tier2_tokens"], current, "T2 +30%", "T2")
            total_pnl += pnl
            with sqlite3.connect(DB_PATH) as db:
                db.execute("UPDATE positions SET tier2_hit=1 WHERE id=?", (pos["id"],))
            t2_hit = True

        # ── Tier 3: trail last 33% with 8% drop from peak ────────────────────
        if t1_hit and t2_hit:
            trail_stop = new_peak * (1 - TIER3_TRAIL)
            if current <= trail_stop:
                total_pnl += _close_full(pos, current, "TRAIL")
                continue

        # ── If both T1 and T2 hit and T3 still open, close position record ───
        # (position stays OPEN until T3 exits)

    if total_pnl != 0:
        print(f"  [PAPER] ── Cycle PnL: ${total_pnl:+.2f} ──")


# ══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def print_dashboard():
    cash      = get_portfolio()
    positions = get_open_positions()

    with sqlite3.connect(DB_PATH) as db:
        closed = db.execute(
            "SELECT COUNT(*), SUM(pnl_usd), AVG(pnl_pct) FROM positions WHERE status='CLOSED'"
        ).fetchone()
        wins = db.execute(
            "SELECT COUNT(*) FROM positions WHERE status='CLOSED' AND pnl_usd > 0"
        ).fetchone()[0]
        losses = db.execute(
            "SELECT COUNT(*) FROM positions WHERE status='CLOSED' AND pnl_usd <= 0"
        ).fetchone()[0]
        recent = db.execute(
            "SELECT token, action, price, pnl_pct, reason, timestamp FROM trade_log ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()

    total_closed = closed[0] or 0
    total_pnl    = closed[1] or 0
    win_rate     = (wins / max(total_closed, 1)) * 100

    open_value = 0
    for p in positions:
        live = get_current_price(p["token"], p.get("mint", ""))
        price = live or p["entry_price"]
        remaining = p["tier3_tokens"]
        if not p["tier1_hit"]:
            remaining += p["tier1_tokens"]
        if not p["tier2_hit"]:
            remaining += p["tier2_tokens"]
        open_value += remaining * price

    portfolio_value = cash + open_value

    print(f"""
╔══════════════════════════════════════════════════╗
║         BR0THA PAPER TRADING DASHBOARD          ║
╠══════════════════════════════════════════════════╣
║ Starting Capital:  $1000.00                     ║
║ Cash Available:    ${cash:>10.2f}               ║
║ Open Value:        ${open_value:>10.2f}         ║
║ Portfolio Total:   ${portfolio_value:>10.2f}    ║
║ Realized PnL:      ${total_pnl:>+10.2f}         ║
║ Win Rate:          {win_rate:>6.1f}% ({wins}W / {losses}L)    ║
╠══════════════════════════════════════════════════╣
║ EXIT RULES: T1 +15% | T2 +30% | T3 8% trail    ║
║ HARD STOP: -12% | COOLDOWN: 24h after SL        ║
╠══════════════════════════════════════════════════╣""")

    if positions:
        print("║ OPEN POSITIONS:                                  ║")
        for p in positions:
            pnl = p.get("pnl_pct", 0)
            bar = "🟢" if pnl > 0 else "🔴"
            t1  = "✅" if p["tier1_hit"] else "○"
            t2  = "✅" if p["tier2_hit"] else "○"
            peak_pct = ((p["peak_price"] - p["entry_price"]) / p["entry_price"] * 100) if p["entry_price"] else 0
            print(f"║  {bar} {p['token']:10} {pnl:+.1f}%  T1{t1} T2{t2} peak={peak_pct:+.1f}%  ║")

    print("╠══════════════════════════════════════════════════╣")
    print("║ RECENT TRADES:                                   ║")
    for t in recent:
        token, action, price, pnl, reason, ts = t
        ts_short = ts[11:16] if ts else "?"
        pnl_str  = f"{pnl:+.1f}%" if pnl else "    "
        print(f"║  {action:10} {token:10} ${price:.6f} {pnl_str} [{ts_short}] ║")
    print("╚══════════════════════════════════════════════════╝")


# Legacy alias so loop.py calling open_position() still works
def close_position(pos, current_price, reason):
    """Legacy single-exit — now routes through smart tiered system."""
    return _close_full(pos, current_price, reason)


if __name__ == "__main__":
    init_paper_db()
    print_dashboard()
