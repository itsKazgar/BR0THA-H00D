"""
trading.py — BR0THER-H00D Trading Engine
Rules:
- Max 3 open trades at once
- Max 20% of portfolio per trade
- 50% of wallet always untouched (reserve)
- Take profit at 60%, leave 10% to compound
- Min market cap: $35k
- Fast scalper — in and out
- Dynamic slippage
- Never go all in
- 0.2 SOL/week for trading access

SECURITY NOTES:
- Private keys are NEVER stored in the database or on disk.
- When a wallet is created, the private key is shown to the user ONCE and then discarded.
- All API keys must be set via environment variables in your .env file.
"""

import os, sqlite3, json, time, asyncio, logging, requests, httpx
from solders.keypair import Keypair
from base58 import b58encode

logger = logging.getLogger(__name__)

DB_PATH        = "data/agent.db"

# ── API CONFIG — loaded from .env only, never hardcoded ───────────────────────
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
HELIUS_RPC_URL = (
    f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    if HELIUS_API_KEY
    else "https://api.mainnet-beta.solana.com"
)
JUPITER_QUOTE  = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP   = "https://api.jup.ag/swap/v1/swap"

SOL_MINT       = "So11111111111111111111111111111111111111112"
USDC_MINT      = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ── RISK RULES ─────────────────────────────────────────────────────────────────
MAX_OPEN_TRADES    = 3        # never more than 3 at once
MAX_POSITION_PCT   = 0.25     # max 20% of tradeable balance per trade
RESERVE_PCT        = 0.50     # 50% of wallet always untouched
TAKE_PROFIT_PCT    = 0.15     # take profit at +60%
LEAVE_IN_PCT       = 0.10     # leave 10% in after TP to compound
STOP_LOSS_PCT      = -0.07    # cut at -25%
MIN_MCAP_USD       = 35_000   # minimum $35k market cap
TRADING_WEEK_SOL   = 0.2      # 0.2 SOL per week for trading access
BOT_FEE_PCT        = 0.005    # 0.5% fee on each trade

# ── DB HELPERS ─────────────────────────────────────────────────────────────────
def init_trading_tables():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS trading_subscriptions (
            user_id TEXT PRIMARY KEY,
            expires_at REAL DEFAULT 0,
            sol_paid REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS open_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            token_mint TEXT,
            token_symbol TEXT,
            entry_price REAL,
            amount_sol REAL,
            tokens_held REAL,
            entry_ts REAL DEFAULT (unixepoch()),
            status TEXT DEFAULT 'open',
            strategy TEXT DEFAULT 'manual',
            tp_hit INTEGER DEFAULT 0,
            tokens_remaining REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            token_mint TEXT,
            token_symbol TEXT,
            action TEXT,
            amount_sol REAL,
            price REAL,
            pnl_sol REAL DEFAULT 0,
            signature TEXT,
            ts REAL DEFAULT (unixepoch())
        );
        CREATE TABLE IF NOT EXISTS dca_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            token_mint TEXT,
            token_symbol TEXT,
            amount_sol_per_buy REAL,
            interval_seconds INTEGER,
            max_buys INTEGER,
            buys_done INTEGER DEFAULT 0,
            last_buy REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            ts REAL DEFAULT (unixepoch())
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            token_mint TEXT,
            token_symbol TEXT,
            signal_type TEXT,
            target_price REAL,
            triggered INTEGER DEFAULT 0,
            ts REAL DEFAULT (unixepoch())
        );
        CREATE TABLE IF NOT EXISTS auto_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            strategy_type TEXT,
            config TEXT DEFAULT '{}',
            active INTEGER DEFAULT 1,
            ts REAL DEFAULT (unixepoch())
        );
        """)

# ── SUBSCRIPTION ───────────────────────────────────────────────────────────────
def is_trading_subscriber(user_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT expires_at FROM trading_subscriptions WHERE user_id=?", (user_id,)
        ).fetchone()
    return bool(row and row[0] > time.time())

def get_subscription_info(user_id: str) -> dict:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT expires_at, sol_paid FROM trading_subscriptions WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        return {"active": False, "expires_at": 0, "sol_paid": 0}
    return {"active": row[0] > time.time(), "expires_at": row[0], "sol_paid": row[1]}

def activate_trading_sub(user_id: str, sol_paid: float):
    now     = time.time()
    expires = now + (7 * 24 * 3600)  # 1 week
    with sqlite3.connect(DB_PATH) as db:
        existing = db.execute(
            "SELECT expires_at FROM trading_subscriptions WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing and existing[0] > now:
            expires = existing[0] + (7 * 24 * 3600)
        db.execute(
            "INSERT OR REPLACE INTO trading_subscriptions (user_id, expires_at, sol_paid) VALUES (?,?,?)",
            (user_id, expires, sol_paid)
        )

# ── WALLET ─────────────────────────────────────────────────────────────────────
def create_wallet() -> dict:
    """
    Generate a brand-new Solana keypair.

    Returns the address AND private key so the caller (the bot) can display
    the private key to the user ONCE.  The private key is NOT stored anywhere
    — it is the user's responsibility to save it.

    Returns:
        {"address": str, "private_key_b58": str}
    """
    kp      = Keypair()
    address = str(kp.pubkey())
    private = b58encode(bytes(kp)).decode()
    return {"address": address, "private_key_b58": private}

def save_wallet_address(user_id: str, address: str):
    """
    Store ONLY the public wallet address in the database.
    Never call this with a private key.
    """
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "UPDATE users SET wallet_address=? WHERE user_id=?",
            (address, user_id)
        )

def get_user_wallet(user_id: str) -> dict | None:
    """Returns {"address": str} or None. Never returns a private key."""
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT wallet_address FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    if row and row[0]:
        return {"address": row[0]}
    return None

async def get_sol_balance(address: str) -> float:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getBalance",
                "params": [address]
            })
        return r.json()["result"]["value"] / 1e9
    except:
        return 0.0

def get_sol_balance_sync(address: str) -> float:
    try:
        r = requests.post(HELIUS_RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getBalance",
            "params": [address]
        }, timeout=10)
        return r.json()["result"]["value"] / 1e9
    except:
        return 0.0

# ── RISK ENGINE ────────────────────────────────────────────────────────────────
def get_open_trade_count(user_id: str) -> int:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT COUNT(*) FROM open_positions WHERE user_id=? AND status='open'", (user_id,)
        ).fetchone()
    return row[0] if row else 0

def get_tradeable_balance(total_sol: float) -> float:
    """50% reserve always untouched. Returns max tradeable amount."""
    return total_sol * (1 - RESERVE_PCT)

def get_max_position_size(tradeable_sol: float) -> float:
    """Max 20% of tradeable balance per trade."""
    return tradeable_sol * MAX_POSITION_PCT

def check_risk_rules(user_id: str, amount_sol: float, wallet_balance: float) -> tuple[bool, str]:
    """Returns (ok, reason). Enforces all risk rules."""
    tradeable  = get_tradeable_balance(wallet_balance)
    max_pos    = get_max_position_size(tradeable)
    open_count = get_open_trade_count(user_id)

    if open_count >= MAX_OPEN_TRADES:
        return False, f"Max {MAX_OPEN_TRADES} open trades at once. Close one first."

    if amount_sol > max_pos:
        return False, (
            f"Position too large.\n"
            f"Max allowed: {max_pos:.4f} SOL (20% of tradeable)\n"
            f"Your balance: {wallet_balance:.4f} SOL\n"
            f"Reserve (untouchable): {wallet_balance * RESERVE_PCT:.4f} SOL"
        )

    reserve = wallet_balance * RESERVE_PCT
    if (wallet_balance - amount_sol) < reserve:
        return False, f"Would break 50% reserve rule. Keep at least {reserve:.4f} SOL safe."

    return True, ""

# ── TOKEN INFO ─────────────────────────────────────────────────────────────────
def get_token_info(mint: str) -> dict:
    """Get token price, mcap, liquidity from DexScreener."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=10
        )
        pairs = r.json().get("pairs", [])
        if not pairs:
            return {"ok": False, "error": "No trading pairs found"}
        pair = sorted(
            pairs,
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
            reverse=True
        )[0]
        mcap = float(pair.get("fdv") or 0)
        if mcap < MIN_MCAP_USD:
            return {"ok": False, "error": f"Market cap too low (${mcap:,.0f} < ${MIN_MCAP_USD:,} min)"}
        return {
            "ok":         True,
            "price_usd":  float(pair.get("priceUsd") or 0),
            "mcap":       mcap,
            "liquidity":  float(pair.get("liquidity", {}).get("usd") or 0),
            "volume_24h": float(pair.get("volume", {}).get("h24") or 0),
            "change_24h": float(pair.get("priceChange", {}).get("h24") or 0),
            "symbol":     pair.get("baseToken", {}).get("symbol", "???"),
            "name":       pair.get("baseToken", {}).get("name", "Unknown"),
            "dex_url":    pair.get("url", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def search_token(query: str) -> dict:
    """Search for a token by name or symbol."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search/?q={requests.utils.quote(query)}",
            timeout=10
        )
        pairs = r.json().get("pairs", [])
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        if not sol_pairs:
            return {"ok": False, "error": "Token not found on Solana"}
        best = sorted(
            sol_pairs,
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
            reverse=True
        )[0]
        return {
            "ok":      True,
            "mint":    best.get("baseToken", {}).get("address", ""),
            "symbol":  best.get("baseToken", {}).get("symbol", "???"),
            "name":    best.get("baseToken", {}).get("name", ""),
            "price":   float(best.get("priceUsd") or 0),
            "mcap":    float(best.get("fdv") or 0),
            "liq":     float(best.get("liquidity", {}).get("usd") or 0),
            "dex_url": best.get("url", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_dynamic_slippage(liquidity_usd: float, amount_sol: float, sol_price_usd: float = 150) -> int:
    """
    Dynamic slippage based on liquidity vs trade size.
    Low liquidity or large trade = higher slippage tolerance.
    Returns slippage in basis points (100 = 1%).
    """
    trade_usd  = amount_sol * sol_price_usd
    impact_pct = (trade_usd / max(liquidity_usd, 1)) * 100

    if impact_pct < 0.5:
        return 50    # 0.5%
    elif impact_pct < 1:
        return 100   # 1%
    elif impact_pct < 3:
        return 200   # 2%
    elif impact_pct < 5:
        return 300   # 3%
    else:
        return 1000  # 10% max — thin liquidity

# ── JUPITER SWAP ───────────────────────────────────────────────────────────────
async def jupiter_swap(user_id: str, from_token: str, to_token: str, amount_sol: float) -> dict:
    """Execute a real swap via Jupiter — signs and broadcasts on-chain."""
    try:
        # Load private key from .env
        pk_b58 = os.getenv("WALLET_PRIVATE_KEY", "")
        if not pk_b58:
            return {"ok": False, "error": "No WALLET_PRIVATE_KEY set in .env"}

        from base58 import b58decode
        kp = Keypair.from_bytes(b58decode(pk_b58))
        address = str(kp.pubkey())

        known = {
            "sol":  SOL_MINT,
            "usdc": USDC_MINT,
        }
        brotha_mint = os.getenv("BROTHA_MINT", "")
        if brotha_mint:
            known["brotha"] = brotha_mint

        from_mint = known.get(from_token.lower(), from_token)
        to_mint   = known.get(to_token.lower(), to_token)

        bal = get_sol_balance_sync(address)
        ok, reason = check_risk_rules(user_id, amount_sol, bal)
        if not ok:
            return {"ok": False, "error": reason}

        token_info = get_token_info(to_mint) if from_mint == SOL_MINT else {}
        liq        = token_info.get("liquidity", 50000) if token_info.get("ok") else 50000
        slippage   = get_dynamic_slippage(liq, amount_sol)
        amount_lamports = int(amount_sol * 1e9)

        async with httpx.AsyncClient(timeout=15) as c:
            # Step 1: Get quote
            quote_resp = await c.get(JUPITER_QUOTE, params={
                "inputMint":   from_mint,
                "outputMint":  to_mint,
                "amount":      amount_lamports,
                "slippageBps": slippage,
            })
            quote = quote_resp.json()
            if "error" in quote:
                return {"ok": False, "error": quote["error"]}

            out_amount   = int(quote.get("outAmount", 0))
            price_impact = float(quote.get("priceImpactPct", 0))

            if price_impact > 5:
                return {"ok": False, "error": f"Price impact too high: {price_impact:.1f}%. Trade smaller."}

            # Step 2: Get swap transaction
            swap_resp = await c.post(JUPITER_SWAP, json={
                "quoteResponse":         quote,
                "userPublicKey":         address,
                "wrapAndUnwrapSol":      True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": 1000,
            })
            swap_data = swap_resp.json()
            if "error" in swap_data:
                return {"ok": False, "error": swap_data["error"]}

        # Step 3: Sign and send
        import base64
        from solders.transaction import VersionedTransaction
        from solders.keypair import Keypair as SoldersKeypair

        raw_tx = base64.b64decode(swap_data["swapTransaction"])
        tx = VersionedTransaction.from_bytes(raw_tx)
        signed_tx = VersionedTransaction(tx.message, [kp])
        signed_bytes = base64.b64encode(bytes(signed_tx)).decode("utf-8")

        async with httpx.AsyncClient(timeout=30) as c:
            send_resp = await c.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [signed_bytes, {"encoding": "base64", "skipPreflight": False}]
            })
        result = send_resp.json()
        if "error" in result:
            return {"ok": False, "error": str(result["error"])}

        signature = result.get("result", "unknown")
        symbol = token_info.get("symbol", to_token.upper()) if token_info.get("ok") else to_token.upper()
        price  = token_info.get("price_usd", 0) if token_info.get("ok") else 0

        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                "INSERT INTO trade_history (user_id,token_mint,token_symbol,action,amount_sol,price,signature) VALUES (?,?,?,?,?,?,?)",
                (user_id, to_mint, symbol, "buy", amount_sol, price, signature)
            )
            if from_mint == SOL_MINT:
                db.execute(
                    "INSERT INTO open_positions (user_id,token_mint,token_symbol,entry_price,amount_sol,tokens_held,tokens_remaining,strategy) VALUES (?,?,?,?,?,?,?,?)",
                    (user_id, to_mint, symbol, price, amount_sol, out_amount, out_amount, "manual")
                )

        return {
            "ok":           True,
            "from":         from_token.upper(),
            "to":           symbol,
            "amount":       amount_sol,
            "out_amount":   out_amount,
            "slippage_bps": slippage,
            "price_impact": price_impact,
            "signature":    signature,
            "explorer":     f"https://solscan.io/tx/{signature}",
        }

    except Exception as e:
        logger.error(f"Swap error: {e}")
        return {"ok": False, "error": str(e)}
# ── POSITION MANAGEMENT ────────────────────────────────────────────────────────
def get_open_positions(user_id: str) -> list:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT id,token_mint,token_symbol,entry_price,amount_sol,tokens_held,tokens_remaining,strategy,tp_hit,entry_ts FROM open_positions WHERE user_id=? AND status='open'",
            (user_id,)
        ).fetchall()
    return [
        {
            "id": r[0], "mint": r[1], "symbol": r[2],
            "entry_price": r[3], "amount_sol": r[4],
            "tokens_held": r[5], "tokens_remaining": r[6],
            "strategy": r[7], "tp_hit": r[8], "entry_ts": r[9]
        }
        for r in rows
    ]

def close_position(position_id: int, pnl_sol: float = 0):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "UPDATE open_positions SET status='closed' WHERE id=?", (position_id,)
        )

def get_position_pnl(position: dict) -> dict:
    info = get_token_info(position["mint"])
    if not info["ok"]:
        return {"ok": False, "error": info["error"]}
    current_price = info["price_usd"]
    entry_price   = position["entry_price"]
    if entry_price <= 0:
        return {"ok": False, "error": "Invalid entry price"}
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    return {
        "ok":            True,
        "current_price": current_price,
        "entry_price":   entry_price,
        "pnl_pct":       pnl_pct,
        "pnl_sol":       position["amount_sol"] * (pnl_pct / 100),
        "should_tp":     pnl_pct >= TAKE_PROFIT_PCT * 100,
        "should_sl":     pnl_pct <= STOP_LOSS_PCT * 100,
    }

async def check_and_manage_positions(user_id: str, bot=None) -> list:
    """Check all open positions, auto TP/SL if triggered."""
    positions = get_open_positions(user_id)
    actions   = []
    for pos in positions:
        pnl = get_position_pnl(pos)
        if not pnl["ok"]:
            continue

        if pnl["should_tp"] and not pos["tp_hit"]:
            sell_pct = 1 - LEAVE_IN_PCT
            actions.append({
                "action":   "take_profit",
                "position": pos,
                "pnl":      pnl,
                "sell_pct": sell_pct,
                "message":  (
                    f"🎯 Take Profit hit!\n\n"
                    f"{pos['symbol']} +{pnl['pnl_pct']:.1f}%\n"
                    f"Selling 90% — leaving 10% to compound.\n"
                    f"PnL: +{pnl['pnl_sol']:.4f} SOL"
                )
            })
            with sqlite3.connect(DB_PATH) as db:
                db.execute("UPDATE open_positions SET tp_hit=1 WHERE id=?", (pos["id"],))
            if bot:
                try:
                    await bot.send_message(chat_id=user_id, text=actions[-1]["message"])
                except:
                    pass

        elif pnl["should_sl"]:
            actions.append({
                "action":   "stop_loss",
                "position": pos,
                "pnl":      pnl,
                "message":  (
                    f"🛑 Stop Loss triggered!\n\n"
                    f"{pos['symbol']} {pnl['pnl_pct']:.1f}%\n"
                    f"Cutting the trade. Live to fight another day.\n"
                    f"PnL: {pnl['pnl_sol']:.4f} SOL"
                )
            })
            close_position(pos["id"], pnl["pnl_sol"])
            if bot:
                try:
                    await bot.send_message(chat_id=user_id, text=actions[-1]["message"])
                except:
                    pass

    return actions

# ── DCA ────────────────────────────────────────────────────────────────────────
def create_dca_plan(user_id: str, mint: str, symbol: str, amount_per_buy: float, interval_seconds: int, max_buys: int):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO dca_plans (user_id,token_mint,token_symbol,amount_sol_per_buy,interval_seconds,max_buys) VALUES (?,?,?,?,?,?)",
            (user_id, mint, symbol, amount_per_buy, interval_seconds, max_buys)
        )

def get_dca_plans(user_id: str) -> list:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT id,token_symbol,amount_sol_per_buy,interval_seconds,max_buys,buys_done,active FROM dca_plans WHERE user_id=?",
            (user_id,)
        ).fetchall()
    return [
        {
            "id": r[0], "symbol": r[1], "amount_per_buy": r[2],
            "interval": r[3], "max_buys": r[4], "buys_done": r[5], "active": r[6]
        }
        for r in rows
    ]

def cancel_dca(user_id: str, plan_id: int):
    with sqlite3.connect(DB_PATH) as db:
        db.execute("UPDATE dca_plans SET active=0 WHERE id=? AND user_id=?", (plan_id, user_id))

async def run_dca_plans(bot=None):
    """Background loop to execute DCA plans."""
    now = time.time()
    with sqlite3.connect(DB_PATH) as db:
        plans = db.execute(
            "SELECT id,user_id,token_mint,token_symbol,amount_sol_per_buy,interval_seconds,max_buys,buys_done,last_buy FROM dca_plans WHERE active=1"
        ).fetchall()
    for plan in plans:
        pid, uid, mint, symbol, amount, interval, max_buys, done, last_buy = plan
        if done >= max_buys:
            with sqlite3.connect(DB_PATH) as db:
                db.execute("UPDATE dca_plans SET active=0 WHERE id=?", (pid,))
            continue
        if now - last_buy < interval:
            continue
        res = await jupiter_swap(uid, "sol", mint, amount)
        msg = (
            f"🔄 DCA Buy #{done+1}/{max_buys}\n\n"
            f"Token: {symbol}\nAmount: {amount} SOL\n"
            f"{'✅ Done' if res['ok'] else 'Failed: ' + res['error']}"
        )
        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE dca_plans SET buys_done=buys_done+1, last_buy=? WHERE id=?", (now, pid))
        if bot:
            try:
                await bot.send_message(chat_id=uid, text=msg)
            except:
                pass

# ── SIGNALS ────────────────────────────────────────────────────────────────────
def set_signal(user_id: str, mint: str, symbol: str, signal_type: str, target_price: float):
    """signal_type: 'buy_dip' | 'sell_peak' | 'rebuy_after_sell'"""
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO signals (user_id,token_mint,token_symbol,signal_type,target_price) VALUES (?,?,?,?,?)",
            (user_id, mint, symbol, signal_type, target_price)
        )

def get_signals(user_id: str) -> list:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT id,token_symbol,signal_type,target_price,triggered FROM signals WHERE user_id=? AND triggered=0",
            (user_id,)
        ).fetchall()
    return [{"id": r[0], "symbol": r[1], "type": r[2], "target": r[3], "triggered": r[4]} for r in rows]

async def check_signals(bot=None):
    """Background loop to check and fire signals."""
    with sqlite3.connect(DB_PATH) as db:
        signals = db.execute(
            "SELECT id,user_id,token_mint,token_symbol,signal_type,target_price FROM signals WHERE triggered=0"
        ).fetchall()
    for sig in signals:
        sid, uid, mint, symbol, stype, target = sig
        try:
            info = get_token_info(mint)
            if not info["ok"]:
                continue
            price = info["price_usd"]
            fired = False

            if stype == "buy_dip" and price <= target:
                fired = True
                msg   = f"📉 Buy Dip Signal!\n\n{symbol} hit ${price:.8f}\nTarget was ${target:.8f}\n\nUse /trade to buy."
            elif stype == "sell_peak" and price >= target:
                fired = True
                msg   = f"📈 Sell Peak Signal!\n\n{symbol} hit ${price:.8f}\nTarget was ${target:.8f}\n\nConsider taking profits."
            elif stype == "rebuy_after_sell" and price <= target:
                fired = True
                msg   = f"🔁 Rebuy Signal!\n\n{symbol} back to ${price:.8f}\nGood re-entry point."

            if fired:
                with sqlite3.connect(DB_PATH) as db:
                    db.execute("UPDATE signals SET triggered=1 WHERE id=?", (sid,))
                if bot:
                    try:
                        await bot.send_message(chat_id=uid, text=msg)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Signal check error: {e}")

# ── AUTO STRATEGIES ────────────────────────────────────────────────────────────
def set_auto_strategy(user_id: str, strategy_type: str, config: dict):
    """strategy_type: 'scalp' | 'dip_buyer' | 'trend_follow'"""
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "UPDATE auto_strategies SET active=0 WHERE user_id=? AND strategy_type=?",
            (user_id, strategy_type)
        )
        db.execute(
            "INSERT INTO auto_strategies (user_id,strategy_type,config) VALUES (?,?,?)",
            (user_id, strategy_type, json.dumps(config))
        )

def get_auto_strategies(user_id: str) -> list:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT id,strategy_type,config,active FROM auto_strategies WHERE user_id=?",
            (user_id,)
        ).fetchall()
    return [{"id": r[0], "type": r[1], "config": json.loads(r[2]), "active": r[3]} for r in rows]

# ── PORTFOLIO SUMMARY ──────────────────────────────────────────────────────────
def get_portfolio_summary(user_id: str) -> str:
    positions = get_open_positions(user_id)
    w         = get_user_wallet(user_id)
    bal       = get_sol_balance_sync(w["address"]) if w else 0.0
    tradeable = get_tradeable_balance(bal)
    reserve   = bal * RESERVE_PCT
    used      = sum(p["amount_sol"] for p in positions)

    lines = [
        f"Portfolio\n",
        f"Total:     {bal:.4f} SOL",
        f"Reserve:   {reserve:.4f} SOL (locked 50%)",
        f"Tradeable: {tradeable:.4f} SOL",
        f"In trades: {used:.4f} SOL",
        f"Free:      {max(tradeable - used, 0):.4f} SOL",
        f"Open trades: {len(positions)}/{MAX_OPEN_TRADES}\n",
    ]

    if positions:
        lines.append("Positions:")
        for p in positions:
            pnl = get_position_pnl(p)
            if pnl["ok"]:
                arrow = "📈" if pnl["pnl_pct"] > 0 else "📉"
                lines.append(f"{arrow} {p['symbol']} {pnl['pnl_pct']:+.1f}% ({pnl['pnl_sol']:+.4f} SOL)")
            else:
                lines.append(f"• {p['symbol']} — price unavailable")
    else:
        lines.append("No open positions.")

    return "\n".join(lines)

# ── ALERTS (legacy compat) ─────────────────────────────────────────────────────
def set_alert(user_id: str, coin: str, target: float, direction: str):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO alerts (user_id,coin,target,direction) VALUES (?,?,?,?)",
            (user_id, coin.lower(), target, direction)
        )

def get_alerts(user_id: str) -> list:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT coin,target,direction FROM alerts WHERE user_id=? AND active=1", (user_id,)
        ).fetchall()
    return [{"coin": r[0], "target": r[1], "direction": r[2]} for r in rows]


# ── THESIS ENGINE ──────────────────────────────────────────────────────────────
"""
Theses define WHAT to buy and WHY.
Each thesis is a filter + scoring function over DexScreener data.
"""

THESES = {
    "momentum": {
        "desc": "Buy tokens pumping >20% in 1h with rising volume",
        "min_change_1h": 20,
        "min_volume_24h": 50_000,
        "min_mcap": 50_000,
        "max_mcap": 5_000_000,
        "min_liquidity": 20_000,
    },
    "dip_buy": {
        "desc": "Buy quality tokens down >15% in 24h — mean reversion play",
        "max_change_24h": -15,
        "min_volume_24h": 30_000,
        "min_mcap": 100_000,
        "max_mcap": 10_000_000,
        "min_liquidity": 25_000,
    },
    "breakout": {
        "desc": "Buy tokens with high volume vs mcap ratio — early breakout",
        "min_vol_mcap_ratio": 0.3,   # volume >= 30% of mcap = hot
        "min_mcap": 35_000,
        "max_mcap": 2_000_000,
        "min_liquidity": 15_000,
    },
}

def score_token(pair: dict, thesis: str) -> tuple[bool, float, str]:
    """
    Returns (passes, score, reason).
    Score 0-100. Higher = stronger entry.
    """
    t = THESES.get(thesis)
    if not t:
        return False, 0, "Unknown thesis"

    try:
        mcap     = float(pair.get("fdv") or 0)
        liq      = float(pair.get("liquidity", {}).get("usd") or 0)
        vol_24h  = float(pair.get("volume", {}).get("h24") or 0)
        ch_1h    = float(pair.get("priceChange", {}).get("h1") or 0)
        ch_24h   = float(pair.get("priceChange", {}).get("h24") or 0)
        chain    = pair.get("chainId", "")

        if chain != "solana":
            return False, 0, "Not Solana"
        if mcap < MIN_MCAP_USD:
            return False, 0, f"Mcap too low ${mcap:,.0f}"
        if liq < t.get("min_liquidity", 0):
            return False, 0, f"Low liquidity ${liq:,.0f}"

        if thesis == "momentum":
            if ch_1h < t["min_change_1h"]:
                return False, 0, f"1h change only {ch_1h:.1f}%"
            if vol_24h < t["min_volume_24h"]:
                return False, 0, "Volume too low"
            if not (t["min_mcap"] <= mcap <= t["max_mcap"]):
                return False, 0, "Mcap out of range"
            score = min(ch_1h * 2, 60) + min(vol_24h / 10_000, 40)

        elif thesis == "dip_buy":
            if ch_24h > t["max_change_24h"]:
                return False, 0, f"Not enough dip: {ch_24h:.1f}%"
            if vol_24h < t["min_volume_24h"]:
                return False, 0, "Volume too low"
            if not (t["min_mcap"] <= mcap <= t["max_mcap"]):
                return False, 0, "Mcap out of range"
            score = min(abs(ch_24h) * 2, 50) + min(vol_24h / 5_000, 50)

        elif thesis == "breakout":
            ratio = vol_24h / max(mcap, 1)
            if ratio < t["min_vol_mcap_ratio"]:
                return False, 0, f"Vol/mcap ratio low: {ratio:.2f}"
            if not (t["min_mcap"] <= mcap <= t["max_mcap"]):
                return False, 0, "Mcap out of range"
            score = min(ratio * 100, 70) + min(liq / 1_000, 30)

        else:
            return False, 0, "Unknown thesis"

        return True, round(score, 1), f"{thesis} score {score:.0f}"

    except Exception as e:
        return False, 0, str(e)


def scan_for_thesis(thesis: str, limit: int = 5) -> list[dict]:
    """
    Scan DexScreener trending Solana pairs and score against a thesis.
    Returns top matches sorted by score.
    """
    try:
        r = requests.get(
            "https://api.dexscreener.com/latest/dex/tokens/trending?chainId=solana",
            timeout=15
        )
        pairs = r.json() if isinstance(r.json(), list) else r.json().get("pairs", [])
    except:
        # fallback: search broad
        try:
            r = requests.get(
                "https://api.dexscreener.com/latest/dex/search/?q=solana",
                timeout=15
            )
            pairs = r.json().get("pairs", [])
        except:
            return []

    results = []
    for pair in pairs:
        passes, score, reason = score_token(pair, thesis)
        if passes:
            results.append({
                "mint":    pair.get("baseToken", {}).get("address", ""),
                "symbol":  pair.get("baseToken", {}).get("symbol", "?"),
                "name":    pair.get("baseToken", {}).get("name", ""),
                "price":   float(pair.get("priceUsd") or 0),
                "mcap":    float(pair.get("fdv") or 0),
                "liq":     float(pair.get("liquidity", {}).get("usd") or 0),
                "vol_24h": float(pair.get("volume", {}).get("h24") or 0),
                "ch_1h":   float(pair.get("priceChange", {}).get("h1") or 0),
                "ch_24h":  float(pair.get("priceChange", {}).get("h24") or 0),
                "score":   score,
                "reason":  reason,
                "dex_url": pair.get("url", ""),
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


# ── AUTO TRADE LOOP ────────────────────────────────────────────────────────────
async def run_auto_strategies(bot=None):
    """
    Background loop — runs every 5 minutes.
    For each user with an active auto_strategy, scan + trade if thesis passes.
    Wire this into your bot's background task scheduler.
    """
    with sqlite3.connect(DB_PATH) as db:
        strategies = db.execute(
            "SELECT user_id, strategy_type, config FROM auto_strategies WHERE active=1"
        ).fetchall()

    for uid, stype, cfg_json in strategies:
        try:
            cfg = json.loads(cfg_json)
            thesis   = cfg.get("thesis", stype)
            amount   = float(cfg.get("amount_sol", 0.05))
            max_auto = int(cfg.get("max_auto_trades", 1))

            # Don't exceed open trade limit
            open_count = get_open_trade_count(uid)
            if open_count >= MAX_OPEN_TRADES:
                continue

            auto_open = get_auto_trade_count(uid)
            if auto_open >= max_auto:
                continue

            candidates = scan_for_thesis(thesis, limit=3)
            if not candidates:
                continue

            best = candidates[0]
            if best["score"] < 40:
                continue  # not confident enough

            # Check not already holding this token
            positions = get_open_positions(uid)
            already_in = any(p["mint"] == best["mint"] for p in positions)
            if already_in:
                continue

            result = await jupiter_swap(uid, "sol", best["mint"], amount)

            msg = (
                f"🤖 Auto Trade — {thesis.upper()}\n\n"
                f"Token: {best['symbol']}\n"
                f"Score: {best['score']}/100\n"
                f"Mcap: ${best['mcap']:,.0f}\n"
                f"1h: {best['ch_1h']:+.1f}%  24h: {best['ch_24h']:+.1f}%\n"
                f"Amount: {amount} SOL\n\n"
            )
            if result["ok"]:
                msg += f"✅ Bought!\nTx: {result['explorer']}"
                # Auto-set TP/SL signals
                set_signal(uid, best["mint"], best["symbol"], "sell_peak",
                           best["price"] * (1 + TAKE_PROFIT_PCT))
            else:
                msg += f"❌ Failed: {result['error']}"

            if bot:
                try:
                    await bot.send_message(chat_id=uid, text=msg)
                except:
                    pass

        except Exception as e:
            logger.error(f"Auto strategy error for {uid}: {e}")


def get_auto_trade_count(user_id: str) -> int:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT COUNT(*) FROM open_positions WHERE user_id=? AND status='open' AND strategy!='manual'",
            (user_id,)
        ).fetchone()
    return row[0] if row else 0


def format_thesis_scan(thesis: str, results: list) -> str:
    if not results:
        return f"🔍 No tokens passed the **{thesis}** thesis right now. Market may be quiet."
    t = THESES.get(thesis, {})
    lines = [f"🎯 Thesis: {thesis.upper()}", f"_{t.get('desc', '')}_\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r['symbol']} — Score {r['score']}/100\n"
            f"   Mcap ${r['mcap']:,.0f} | Liq ${r['liq']:,.0f}\n"
            f"   1h {r['ch_1h']:+.1f}% | 24h {r['ch_24h']:+.1f}%\n"
            f"   {r['dex_url']}"
        )
    return "\n".join(lines)


# ── AI THESIS GENERATOR ────────────────────────────────────────────────────────
import httpx, os, json

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

async def ai_generate_thesis(market_context: str = "") -> dict:
    """
    Ask the AI to generate a trading thesis based on current market conditions.
    Returns a thesis config the bot can act on immediately.
    """
    if not OPENROUTER_KEY:
        return {"error": "No OPENROUTER_API_KEY in .env"}

    prompt = f"""You are a Solana memecoin trading bot. Analyze current market conditions and generate ONE trading thesis.

Market context: {market_context or "No context provided — use general crypto market intuition."}

Respond ONLY with a valid JSON object like this:
{{
  "thesis_name": "momentum" | "dip_buy" | "breakout" | "custom",
  "desc": "One sentence explaining the thesis",
  "min_change_1h": <float or null>,
  "max_change_24h": <float or null>,
  "min_volume_24h": <float>,
  "min_mcap": <float>,
  "max_mcap": <float>,
  "min_liquidity": <float>,
  "min_vol_mcap_ratio": <float or null>,
  "confidence": <0-100>,
  "reasoning": "Why this thesis makes sense right now"
}}"""

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={
                    "model": "mistralai/mixtral-8x7b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                }
            )
        content = r.json()["choices"][0]["message"]["content"]
        # Strip markdown fences if present
        content = content.strip().strip("```json").strip("```").strip()
        thesis = json.loads(content)
        # Register it as a live thesis
        THESES[thesis["thesis_name"]] = thesis
        return thesis
    except Exception as e:
        return {"error": str(e)}


# ── MASTER ROBOTS ──────────────────────────────────────────────────────────────
"""
Master robots are named autonomous agents with a personality and strategy.
Each runs independently, manages its own trades, and reports to the user.
"""

MASTER_ROBOTS = {
    "scout": {
        "name":      "Scout",
        "emoji":     "🔭",
        "desc":      "Finds early breakouts. Buys small, exits fast.",
        "thesis":    "breakout",
        "amount":    0.03,
        "tp":        0.40,   # 40% TP
        "sl":        0.15,   # 15% SL — tight
        "interval":  180,    # runs every 3 min
        "max_trades": 2,
    },
    "degen": {
        "name":      "Degen",
        "emoji":     "🎰",
        "desc":      "Momentum chaser. High risk, high reward.",
        "thesis":    "momentum",
        "amount":    0.05,
        "tp":        0.80,
        "sl":        0.30,
        "interval":  300,
        "max_trades": 1,
    },
    "zen": {
        "name":      "Zen",
        "emoji":     "🧘",
        "desc":      "Buys quality dips. Patient and disciplined.",
        "thesis":    "dip_buy",
        "amount":    0.04,
        "tp":        0.60,
        "sl":        0.20,
        "interval":  600,    # runs every 10 min
        "max_trades": 2,
    },
    "oracle": {
        "name":      "Oracle",
        "emoji":     "🔮",
        "desc":      "AI-generated thesis every hour. Adapts to market.",
        "thesis":    "ai",   # dynamically generated
        "amount":    0.04,
        "tp":        0.60,
        "sl":        0.25,
        "interval":  3600,
        "max_trades": 1,
    },
}

def get_active_robots(user_id: str) -> list:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT strategy_type, config FROM auto_strategies WHERE user_id=? AND active=1",
            (user_id,)
        ).fetchall()
    active = []
    for row in rows:
        if row[0].startswith("robot_"):
            robot_id = row[0].replace("robot_", "")
            if robot_id in MASTER_ROBOTS:
                active.append({**MASTER_ROBOTS[robot_id], "id": robot_id, "config": json.loads(row[1])})
    return active

def activate_robot(user_id: str, robot_id: str):
    if robot_id not in MASTER_ROBOTS:
        return False
    robot = MASTER_ROBOTS[robot_id]
    set_auto_strategy(user_id, f"robot_{robot_id}", {
        "robot":      robot_id,
        "thesis":     robot["thesis"],
        "amount_sol": robot["amount"],
        "tp":         robot["tp"],
        "sl":         robot["sl"],
        "max_auto_trades": robot["max_trades"],
    })
    return True

def deactivate_robot(user_id: str, robot_id: str):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "UPDATE auto_strategies SET active=0 WHERE user_id=? AND strategy_type=?",
            (user_id, f"robot_{robot_id}")
        )

async def run_master_robots(bot=None):
    """
    Background loop for all active master robots.
    Each robot runs on its own interval and thesis.
    """
    with sqlite3.connect(DB_PATH) as db:
        strategies = db.execute(
            "SELECT user_id, strategy_type, config FROM auto_strategies WHERE active=1 AND strategy_type LIKE 'robot_%'"
        ).fetchall()

    now = time.time()
    for uid, stype, cfg_json in strategies:
        try:
            robot_id = stype.replace("robot_", "")
            robot    = MASTER_ROBOTS.get(robot_id)
            if not robot:
                continue

            cfg      = json.loads(cfg_json)
            last_run = cfg.get("last_run", 0)
            if now - last_run < robot["interval"]:
                continue

            # Update last_run
            cfg["last_run"] = now
            with sqlite3.connect(DB_PATH) as db:
                db.execute(
                    "UPDATE auto_strategies SET config=? WHERE user_id=? AND strategy_type=?",
                    (json.dumps(cfg), uid, stype)
                )

            thesis = robot["thesis"]

            # Oracle robot generates AI thesis dynamically
            if thesis == "ai":
                generated = await ai_generate_thesis()
                if "error" in generated:
                    continue
                thesis = generated.get("thesis_name", "momentum")

            open_count = get_open_trade_count(uid)
            if open_count >= MAX_OPEN_TRADES:
                continue

            auto_count = get_auto_trade_count(uid)
            if auto_count >= robot["max_trades"]:
                continue

            candidates = scan_for_thesis(thesis, limit=3)
            if not candidates:
                continue

            best = candidates[0]
            if best["score"] < 35:
                continue

            positions = get_open_positions(uid)
            if any(p["mint"] == best["mint"] for p in positions):
                continue

            result = await jupiter_swap(uid, "sol", best["mint"], robot["amount"])

            msg = (
                f"{robot['emoji']} {robot['name']} Robot\n\n"
                f"Thesis: {thesis.upper()}\n"
                f"Token: {best['symbol']} (score {best['score']}/100)\n"
                f"Mcap: ${best['mcap']:,.0f}\n"
                f"1h: {best['ch_1h']:+.1f}% | 24h: {best['ch_24h']:+.1f}%\n"
                f"Amount: {robot['amount']} SOL\n"
                f"TP: +{robot['tp']*100:.0f}% | SL: -{robot['sl']*100:.0f}%\n\n"
            )
            if result["ok"]:
                msg += f"✅ Bought!\n{result['explorer']}"
                set_signal(uid, best["mint"], best["symbol"], "sell_peak",
                           best["price"] * (1 + robot["tp"]))
            else:
                msg += f"❌ Failed: {result['error']}"

            if bot:
                try:
                    await bot.send_message(chat_id=uid, text=msg)
                except:
                    pass

        except Exception as e:
            logger.error(f"Robot {stype} error for {uid}: {e}")
