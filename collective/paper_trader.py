"""
paper_trader.py - BR0THA Paper Trading Engine

Simulates real trades with:
- Position sizing (3% of portfolio per trade)
- Take profit at +40%
- Stop loss at -15%
- Moon bag (keep 20% after TP)
- Realized PnL tracking
"""

import sqlite3, requests, time, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(override=True)

DB_PATH    = "data/agent.db"
PORTFOLIO  = 1000.0  # starting paper portfolio in USD
MAX_TRADE  = 0.03    # 3% max per trade
TP_PCT     = 0.40    # take profit at +40%
SL_PCT     = -0.15   # stop loss at -15%
MOON_BAG   = 0.20    # keep 20% as moon bag after TP

DEX_URL    = "https://api.dexscreener.com/latest/dex/search/?q="
HEADERS    = {"User-Agent": "Mozilla/5.0"}

def init_paper_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id          INTEGER PRIMARY KEY,
            cash_usd    REAL DEFAULT 1000.0,
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            token           TEXT,
            mint            TEXT,
            entry_price     REAL,
            current_price   REAL,
            size_usd        REAL,
            tokens_held     REAL,
            moon_bag_tokens REAL DEFAULT 0,
            tp_price        REAL,
            sl_price        REAL,
            status          TEXT DEFAULT 'OPEN',
            pnl_usd         REAL DEFAULT 0,
            pnl_pct         REAL DEFAULT 0,
            agents_voted    INTEGER,
            confidence      REAL,
            opened_at       TEXT,
            closed_at       TEXT,
            close_reason    TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            token       TEXT,
            action      TEXT,
            price       REAL,
            size_usd    REAL,
            pnl_usd     REAL,
            pnl_pct     REAL,
            reason      TEXT,
            timestamp   TEXT
        );
        """)
        # Init portfolio if empty
        row = db.execute("SELECT * FROM portfolio WHERE id=1").fetchone()
        if not row:
            db.execute("INSERT INTO portfolio VALUES (1, ?, ?)",
                      (PORTFOLIO, datetime.utcnow().isoformat()))

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
        rows = db.execute(
            "SELECT * FROM positions WHERE status='OPEN'"
        ).fetchall()
        cols = [d[0] for d in db.execute("SELECT * FROM positions LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

def get_current_price(token, mint=""):
    """Fetch live price from DexScreener."""
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

def open_position(token, mint, price, agents_voted, confidence):
    """Open a new paper position."""
    cash      = get_portfolio()
    size_usd  = round(cash * MAX_TRADE, 2)

    if size_usd < 5:
        print(f"  [PAPER] Not enough cash to trade (${cash:.2f})")
        return False

    # Check if already in this token
    with sqlite3.connect(DB_PATH) as db:
        existing = db.execute(
            "SELECT id FROM positions WHERE token=? AND status='OPEN'", (token,)
        ).fetchone()
        if existing:
            print(f"  [PAPER] Already holding {token} — skip")
            return False

    price        = float(price or 0)
    if price <= 0:
        print(f"  [PAPER] Invalid price for {token}")
        return False

    tokens_held  = size_usd / price
    tp_price     = price * (1 + TP_PCT)
    sl_price     = price * (1 + SL_PCT)
    moon_bag     = tokens_held * MOON_BAG

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            INSERT INTO positions
            (token, mint, entry_price, current_price, size_usd, tokens_held,
             moon_bag_tokens, tp_price, sl_price, status, agents_voted,
             confidence, opened_at)
            VALUES (?,?,?,?,?,?,?,?,?,'OPEN',?,?,?)
        """, (token, mint, price, price, size_usd, tokens_held,
              moon_bag, tp_price, sl_price,
              agents_voted, confidence, datetime.utcnow().isoformat()))

        db.execute("""
            INSERT INTO trade_log (token, action, price, size_usd, pnl_usd, pnl_pct, reason, timestamp)
            VALUES (?,?,?,?,0,0,'OPEN',?)
        """, (token, "BUY", price, size_usd, datetime.utcnow().isoformat()))

    update_portfolio(cash - size_usd)

    print(f"  [PAPER] 🟢 BUY  {token} @ ${price:.8f}")
    print(f"          Size: ${size_usd:.2f} | Tokens: {tokens_held:.2f}")
    print(f"          TP: ${tp_price:.8f} (+40%) | SL: ${sl_price:.8f} (-15%)")
    print(f"          Portfolio cash remaining: ${cash - size_usd:.2f}")
    return True

def close_position(pos, current_price, reason):
    """Close a position and record PnL."""
    entry       = pos["entry_price"]
    tokens      = pos["tokens_held"]
    moon_bag    = pos["moon_bag_tokens"]
    size_usd    = pos["size_usd"]

    if reason == "TP":
        # Sell main position, keep moon bag
        sell_tokens = tokens - moon_bag
        sell_value  = sell_tokens * current_price
        moon_value  = moon_bag * current_price
        pnl_usd     = sell_value - (size_usd * (1 - MOON_BAG))
        pnl_pct     = ((current_price - entry) / entry) * 100
        print(f"  [PAPER] 🎯 TP HIT {pos['token']} @ ${current_price:.8f} (+{pnl_pct:.1f}%)")
        print(f"          Sold {sell_tokens:.2f} tokens for ${sell_value:.2f}")
        print(f"          Moon bag: {moon_bag:.2f} tokens worth ${moon_value:.2f}")
        cash_back = sell_value
    else:
        # Full exit on SL or manual
        sell_value  = tokens * current_price
        pnl_usd     = sell_value - size_usd
        pnl_pct     = ((current_price - entry) / entry) * 100
        moon_value  = 0
        print(f"  [PAPER] 🔴 {'SL' if reason=='SL' else 'EXIT'} {pos['token']} @ ${current_price:.8f} ({pnl_pct:+.1f}%)")
        print(f"          Got back ${sell_value:.2f} | PnL: ${pnl_usd:+.2f}")
        cash_back = sell_value

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            UPDATE positions SET
                status=?, current_price=?, pnl_usd=?, pnl_pct=?,
                closed_at=?, close_reason=?
            WHERE id=?
        """, ("CLOSED", current_price, pnl_usd, pnl_pct,
              datetime.utcnow().isoformat(), reason, pos["id"]))

        db.execute("""
            INSERT INTO trade_log (token, action, price, size_usd, pnl_usd, pnl_pct, reason, timestamp)
            VALUES (?,?,?,?,?,?,?,?)
        """, (pos["token"], "SELL", current_price, sell_value,
              pnl_usd, pnl_pct, reason, datetime.utcnow().isoformat()))

    cash = get_portfolio()
    update_portfolio(cash + cash_back)
    return pnl_usd

def check_positions():
    """Check all open positions for TP/SL. Call every 60s from loop."""
    positions = get_open_positions()
    if not positions:
        return

    print(f"  [PAPER] Checking {len(positions)} open positions...")
    total_pnl = 0

    for pos in positions:
        current = get_current_price(pos["token"], pos.get("mint", ""))
        if not current or current <= 0:
            print(f"  [PAPER] Can't price {pos['token']} — skipping")
            continue

        entry   = pos["entry_price"]
        pnl_pct = ((current - entry) / entry) * 100

        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE positions SET current_price=?, pnl_pct=? WHERE id=?",
                      (current, pnl_pct, pos["id"]))

        print(f"  [PAPER] {pos['token']:12} | entry=${entry:.8f} | now=${current:.8f} | {pnl_pct:+.1f}%")

        if current >= pos["tp_price"]:
            pnl = close_position(pos, current, "TP")
            total_pnl += pnl
        elif current <= pos["sl_price"]:
            pnl = close_position(pos, current, "SL")
            total_pnl += pnl

    if total_pnl != 0:
        print(f"  [PAPER] Cycle PnL: ${total_pnl:+.2f}")

def print_dashboard():
    """Print full portfolio summary."""
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

    total_closed   = closed[0] or 0
    total_pnl      = closed[1] or 0
    open_value     = sum(
        (p["tokens_held"] * (get_current_price(p["token"], p.get("mint","")) or p["entry_price"]))
        for p in positions
    )
    portfolio_value = cash + open_value + total_pnl
    win_rate        = (wins / max(total_closed, 1)) * 100

    print(f"""
╔══════════════════════════════════════════════════╗
║         BR0THA PAPER TRADING DASHBOARD          ║
╠══════════════════════════════════════════════════╣
║ Starting Capital:  $1000.00                     ║
║ Cash Available:    ${cash:>10.2f}                     ║
║ Open Positions:    {len(positions):>3}                          ║
║ Total PnL:         ${total_pnl:>+10.2f}                     ║
║ Win Rate:          {win_rate:>6.1f}% ({wins}W / {losses}L)              ║
╠══════════════════════════════════════════════════╣""")

    if positions:
        print("║ OPEN POSITIONS:                                  ║")
        for p in positions:
            pnl = p.get("pnl_pct", 0)
            bar = "🟢" if pnl > 0 else "🔴"
            print(f"║  {bar} {p['token']:10} | entry=${p['entry_price']:.6f} | {pnl:+.1f}%  ║")

    print("╠══════════════════════════════════════════════════╣")
    print("║ RECENT TRADES:                                   ║")
    for t in recent:
        token, action, price, pnl, reason, ts = t
        ts_short = ts[11:16] if ts else "?"
        print(f"║  {action:4} {token:10} @ ${price:.6f} {pnl:+.1f}% [{ts_short}]  ║")
    print("╚══════════════════════════════════════════════════╝")

if __name__ == "__main__":
    init_paper_db()
    print_dashboard()
