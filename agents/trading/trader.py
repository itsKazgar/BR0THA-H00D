CY='';GR='';YL='';RD='';BD='';DM='';RS=''
import sys, os, time, requests
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain
from core.consensus import council_vote
from core import analyst, jupiter

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════
LIVE_MODE        = os.getenv("TRADE_MODE", "paper").lower() == "live"
WALLET_KEY       = os.getenv("WALLET_PRIVATE_KEY", "")

PAPER_BALANCE    = 100.0      # starting paper USD balance

# ── Position sizing (confidence-scaled, never all-in) ──────
# score 75-84  → 6% of balance
# score 85-89  → 8% of balance
# score 90-94  → 10% of balance
# score 95+    → 13% of balance
# Hard cap: never more than 15% of balance in one trade
MAX_TRADE_PCT    = 0.15       # absolute hard cap
MIN_TRADE_PCT    = 0.06       # floor for any trade

MAX_POSITIONS    = 3
MIN_SCORE        = 75
MIN_CONFIDENCE   = 50

# ── Exit config ────────────────────────────────────────────
TAKE_PROFIT_PCT  = 0.04       # base TP +4%
STOP_LOSS_PCT    = 0.06       # base SL -6%
MAX_HOLD_MINS    = 5
CHECK_INTERVAL   = 10

SLIPPAGE_BPS     = 150        # 1.5% slippage tolerance

# ── Fee safety ─────────────────────────────────────────────
# In live mode: always keep 0.05 SOL untouched for gas fees
# In paper mode: keep $1.50 buffer
SOL_GAS_RESERVE  = 0.05       # SOL kept for gas (live)
FEE_RESERVE_USD  = 1.50       # USD kept as buffer (paper)
TRADE_BUFFER_USD = 0.50       # extra buffer per trade

# ── Price sanity ───────────────────────────────────────────
MAX_PRICE_MOVE_SANITY = 0.75

# ── Cooldowns ──────────────────────────────────────────────
COOLDOWN_STOP  = 120
COOLDOWN_HOLD  = 30
# ═══════════════════════════════════════════════════════════

SOL_MINT = "So11111111111111111111111111111111111111112"

acted_on   = set()
cooldown   = {}
loss_count = {}
blacklist  = set()


def is_on_cooldown(mint, name=""):
    if mint not in cooldown:
        return False
    elapsed = (time.time() - cooldown[mint]["ts"]) / 60
    limit   = cooldown[mint]["mins"]
    if elapsed >= limit:
        del cooldown[mint]
        return False
    remaining = int(limit - elapsed)
    if name:
        print(f"  [trader] ⏳ {name} cooldown — {remaining} mins left")
    return True


def get_sol_price_usd() -> float:
    """Fetch SOL/USD price — tries two sources."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=6)
        return float(r.json()["solana"]["usd"])
    except Exception:
        pass
    try:
        r = requests.get(
            "https://price.jup.ag/v6/price?ids=SOL",
            timeout=6)
        return float(r.json()["data"]["SOL"]["price"])
    except Exception:
        return 0.0


def get_live_sol_balance(keypair) -> float:
    """Fetch real SOL balance from chain. Returns -1 on failure."""
    try:
        pub = str(keypair.pubkey())
        r   = requests.post(
            "https://api.mainnet-beta.solana.com",
            json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[pub]},
            timeout=8)
        lamports = r.json()["result"]["value"]
        return lamports / 1_000_000_000
    except Exception:
        return -1.0


def usd_to_sol(usd: float, sol_price: float) -> float:
    if sol_price <= 0:
        return 0.0
    return usd / sol_price


def format_balance(usd: float, sol_price: float) -> str:
    if sol_price > 0:
        sol_amt = usd_to_sol(usd, sol_price)
        return f"◎{sol_amt:.4f} SOL  (${usd:.2f})"
    return f"${usd:.2f}"


def score_to_size_pct(score: int, confidence: int) -> float:
    """Scale position size by signal quality. Never above MAX_TRADE_PCT."""
    if score >= 95 and confidence >= 80:
        pct = 0.13
    elif score >= 90 and confidence >= 70:
        pct = 0.10
    elif score >= 85:
        pct = 0.08
    else:
        pct = MIN_TRADE_PCT
    return min(pct, MAX_TRADE_PCT)


class Trader:
    def __init__(self):
        brain.init_db()
        self.mode    = "LIVE" if LIVE_MODE else "PAPER"
        self.keypair = self._load_wallet()

        agent_key    = "trader_live" if LIVE_MODE else "trader_paper"
        s            = brain.load_state(agent_key)

        self.balance           = s.get("balance", PAPER_BALANCE)
        self.total_pnl         = s.get("total_pnl", 0.0)
        self.trades            = s.get("trades", 0)
        self.positions         = s.get("positions", {})
        self.history           = s.get("history", [])
        self.session_trades    = []
        self.day_start_balance = s.get("day_start_balance", self.balance)

        # Fetch SOL price first — needed for live balance sync
        self.sol_price = get_sol_price_usd()

        # LIVE: always sync real wallet balance on startup
        if LIVE_MODE and self.keypair:
            self._sync_live_balance(startup=True)

        self._print_banner()

    # ── Wallet ─────────────────────────────────────────────

    def _load_wallet(self):
        if not LIVE_MODE:
            return None
        if not WALLET_KEY:
            print("""
❌  LIVE_MODE=True but no wallet key found.

  Run:  python add_wallet.py
  Or set WALLET_PRIVATE_KEY in your .env file.
  Export from Phantom: Settings > Security > Export Private Key
""")
            sys.exit(1)
        try:
            from solders.keypair import Keypair
            import base58
            kp = Keypair.from_bytes(base58.b58decode(WALLET_KEY))
            print(f"  [wallet] ✅ loaded — pubkey: {str(kp.pubkey())[:12]}...")
            return kp
        except Exception as e:
            print(f"❌  Bad wallet key: {e}")
            sys.exit(1)

    def _sync_live_balance(self, startup=False):
        """Pull real SOL balance from chain and update self.balance."""
        if not (LIVE_MODE and self.keypair):
            return
        sol_amt = get_live_sol_balance(self.keypair)
        if sol_amt < 0:
            if startup:
                print(f"  [wallet] ⚠️  could not fetch live balance — using saved (${self.balance:.2f})")
            return
        if self.sol_price > 0:
            self.balance = sol_amt * self.sol_price
        if startup:
            self.day_start_balance = self.balance
            self.live_sol_balance  = sol_amt
            print(f"  [wallet] 🔴 LIVE — ◎{sol_amt:.4f} SOL  (${self.balance:.2f})")

    def _refresh_sol_price(self):
        p = get_sol_price_usd()
        if p > 0:
            self.sol_price = p

    # ── Balance helpers ────────────────────────────────────

    def _usable_balance(self) -> float:
        """Balance available to trade — always keeps gas reserve."""
        if LIVE_MODE and self.keypair and self.sol_price > 0:
            # Keep SOL_GAS_RESERVE SOL untouched for gas
            gas_usd = SOL_GAS_RESERVE * self.sol_price
            return self.balance - gas_usd - TRADE_BUFFER_USD
        return self.balance - FEE_RESERVE_USD - TRADE_BUFFER_USD

    # ── Display ────────────────────────────────────────────

    def _print_banner(self):
        mode_color = GR if self.mode == "PAPER" else RD
        bal_str    = format_balance(self.balance, self.sol_price)
        pnl_color  = GR if self.total_pnl >= 0 else RD
        print(f"""
{CY}{BD}╔══════════════════════════════════════════════╗
║  🤖 BR0THER TRADER  {RS}{mode_color}{BD}[{self.mode} MODE]{RS}{CY}{BD}              ║
╠══════════════════════════════════════════════╣{RS}
  {DM}💰 Balance   {RS}  {GR}{BD}{bal_str}{RS}
  {DM}📂 Positions {RS}  {BD}{len(self.positions)}{RS}
  {DM}📈 Total PnL {RS}  {pnl_color}{BD}${self.total_pnl:+.2f}{RS}
  {DM}🔁 Trades    {RS}  {BD}{self.trades}{RS}
  {DM}🧠 AI mode   {RS}  {__import__("core.llm", fromlist=["status"]).status()}
  {DM}🎯 TP / SL   {RS}  {GR}+{TAKE_PROFIT_PCT*100:.0f}%{RS} / {RD}-{STOP_LOSS_PCT*100:.0f}%{RS}
  {DM}⏱  Max hold  {RS}  {MAX_HOLD_MINS} mins
  {DM}📐 Sizing    {RS}  {BD}6-13% confidence-scaled  |  max {MAX_TRADE_PCT*100:.0f}%{RS}
  {DM}🔒 Gas guard {RS}  {RD}◎{SOL_GAS_RESERVE} SOL reserved (live)  /  ${FEE_RESERVE_USD:.2f} (paper){RS}
{CY}{BD}╚══════════════════════════════════════════════╝{RS}""")

    def _save(self):
        brain.save_state("trader_live" if LIVE_MODE else "trader_paper", {
            "balance":           self.balance,
            "positions":         self.positions,
            "total_pnl":         self.total_pnl,
            "trades":            self.trades,
            "history":           self.history[-100:],
            "day_start_balance": self.day_start_balance,
            "updated":           datetime.now().isoformat(),
        })

    def _print_stats(self):
        if not self.history:
            return
        wins     = [t for t in self.history if t["pnl_pct"] > 0]
        losses   = [t for t in self.history if t["pnl_pct"] <= 0]
        total    = len(self.history)
        win_rate = len(wins) / total * 100 if total else 0
        avg_win  = sum(t["pnl_pct"] for t in wins)  / len(wins)  if wins   else 0
        avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
        best     = max(self.history, key=lambda t: t["pnl_pct"])
        worst    = min(self.history, key=lambda t: t["pnl_pct"])
        avg_hold = sum(t["held_mins"] for t in self.history) / total if total else 0
        bal_str  = format_balance(self.balance, self.sol_price)
        mode_tag = "LIVE" if LIVE_MODE else "PAPER"
        print(f"\n  📊 {mode_tag} STATS ({total} trades) | WR={win_rate:.0f}% | "
              f"avg_win=+{avg_win:.1f}% avg_loss={avg_loss:.1f}% | "
              f"best={best['name']} +{best['pnl_pct']:.1f}% | "
              f"worst={worst['name']} {worst['pnl_pct']:.1f}% | "
              f"hold={avg_hold:.0f}min | bal={bal_str} pnl=${self.total_pnl:+.2f}")
        print(f"  📡 Sources: {self._top_sources()}")

    def _top_sources(self):
        src_wins  = {}
        src_total = {}
        for t in self.history:
            for s in t.get("sources", []):
                src_total[s] = src_total.get(s, 0) + 1
                if t["pnl_pct"] > 0:
                    src_wins[s] = src_wins.get(s, 0) + 1
        if not src_total:
            return "no data yet"
        return "  ".join(
            f"{s}({src_wins.get(s,0)}/{t})"
            for s, t in sorted(src_total.items(), key=lambda x: -x[1])
        )

    # ── Market data ────────────────────────────────────────

    def get_market_data(self, mint):
        try:
            r = requests.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
                timeout=8)
            pairs = [p for p in r.json().get("pairs", []) if p.get("chainId") == "solana"]
            if not pairs:
                return None
            best = sorted(pairs,
                key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0),
                reverse=True)[0]
            price = float(best.get("priceUsd", 0) or 0)
            if not price:
                return None
            return {
                "price":     price,
                "change_5m": float(best.get("priceChange", {}).get("m5", 0) or 0),
                "change_1h": float(best.get("priceChange", {}).get("h1", 0) or 0),
                "buys":      int(best.get("txns", {}).get("h1", {}).get("buys", 0) or 0),
                "sells":     int(best.get("txns", {}).get("h1", {}).get("sells", 0) or 0),
                "liq":       float(best.get("liquidity", {}).get("usd", 0) or 0),
                "vol_1h":    float(best.get("volume", {}).get("h1", 0) or 0),
            }
        except Exception:
            return None

    def get_price(self, mint, context=""):
        md = self.get_market_data(mint)
        return md["price"] if md else None

    def _price_is_sane(self, entry: float, current: float) -> bool:
        if entry <= 0 or current <= 0:
            return False
        move = abs(current - entry) / entry
        if move > MAX_PRICE_MOVE_SANITY:
            print(f"  [trader] ⚠️  price sanity FAILED: entry={entry:.8f} "
                  f"current={current:.8f} move={move:.0%} — skipping")
            return False
        return True

    # ── BUY ────────────────────────────────────────────────

    def buy(self, coin: dict, score: int, reasons: list):
        mint = coin.get("mint")
        name = coin.get("name")

        if not mint or not name:
            return
        if mint in self.positions:
            return
        if mint in acted_on:
            return
        if is_on_cooldown(mint, name):
            return
        if mint in blacklist:
            print(f"  [trader] 🚫 {name} blacklisted — lost twice already")
            return
        if mint.endswith("pump"):
            if score < 85:
                print(f"  [trader] 🚫 {name} skipped — pump.fun needs score 85+ (got {score})")
                acted_on.add(mint)
                return
            h1 = coin.get("change_1h", 0)
            if h1 < 0:
                print(f"  [trader] 🚫 {name} skipped — pump.fun needs positive 1h (got {h1:.1f}%)")
                acted_on.add(mint)
                return
        if len(self.positions) >= MAX_POSITIONS:
            print(f"  [trader] max positions ({MAX_POSITIONS}) reached, skipping {name}")
            return
        if len(self.positions) == 2 and score < 85:
            print(f"  [trader] 3rd slot reserved for 85+ score, skipping {name} ({score})")
            return

        # Sync live balance before every trade so sizing is always accurate
        if LIVE_MODE:
            self._sync_live_balance()
            self._refresh_sol_price()

        usable = self._usable_balance()
        if usable < 1:
            sol_str = f" (◎{usd_to_sol(self.balance, self.sol_price):.4f} SOL)" if self.sol_price > 0 else ""
            print(f"  [trader] 🔒 gas reserve guard — usable ${usable:.2f} "
                  f"(balance ${self.balance:.2f}{sol_str})")
            return

        council    = council_vote(coin, score, reasons)
        if not council["approved"]:
            brain.remember("trader",
                f"COUNCIL REJECTED {name} | {council['summary']}",
                type="rejected", tags=f"{name.lower()},rejected")
            return

        decision   = council["results"][0]
        analyst_r  = next((r for r in council["results"] if r["agent"] == "Analyst"), {})
        confidence = analyst_r.get("conf", score)
        thesis     = ", ".join(reasons[:3]) if reasons else f"council approved {council['votes_for']} votes"
        risk_agent = next((r for r in council["results"] if r["agent"] == "Risk Manager"), {})
        risk       = risk_agent.get("reason", "")
        ai_buy     = True
        mode       = decision.get("mode", "rules")

        print(f"\n  [analyst/{mode}] {name}: {'BUY ✅' if ai_buy else 'SKIP ❌'} "
              f"confidence={confidence} | {thesis}")

        if not ai_buy or confidence < MIN_CONFIDENCE:
            brain.remember("trader",
                f"SKIPPED {name} score={score} conf={confidence} | {thesis} | risk={risk}",
                type="skip", tags=f"{name.lower()},skip")
            acted_on.add(mint)
            return

        price = self.get_price(mint, context=f"buy {name}")
        if not price:
            print(f"  [trader] could not get live price for {name} — skipping")
            acted_on.add(mint)
            return

        signal_price = coin.get("price", price)
        if signal_price > 0:
            drift = abs(price - signal_price) / signal_price
            if drift > 0.30:
                if not LIVE_MODE:
                    print(f"  [trader] 📌 {name} price updated {drift:.0%} from signal — using fresh price")
                else:
                    print(f"  [trader] ⚠️  {name} price drifted {drift:.0%} — skipping stale signal")
                    acted_on.add(mint)
                    return

        # ── Confidence-scaled position size ─────────────────
        trade_pct = score_to_size_pct(score, confidence)
        size_usd  = round(min(self.balance * trade_pct, usable), 2)
        if size_usd < 0.50:
            print(f"  [trader] balance too low for safe trade (${self.balance:.2f})")
            return

        tokens = size_usd / price

        age = coin.get("age_hrs", 99)
        if age < 4:
            tp       = round(price * 1.15, 10)
            sl       = round(price * 0.90, 10)
            hold_cap = 20
            mode_tag = "⚡ SCALP"
        else:
            tp       = round(price * (1 + TAKE_PROFIT_PCT), 10)
            sl       = round(price * (1 - STOP_LOSS_PCT), 10)
            hold_cap = MAX_HOLD_MINS
            mode_tag = "📈 SWING"

        sol_size_str = ""
        if self.sol_price > 0:
            sol_size_str = f"  ◎{usd_to_sol(size_usd, self.sol_price):.4f} SOL"

        print(f"  [trader] {mode_tag} mode — age={age:.1f}h TP={tp:.8f} SL={sl:.8f} "
              f"size={trade_pct*100:.0f}% maxhold={hold_cap}min")

        if LIVE_MODE:
            quote, err = jupiter.get_quote(SOL_MINT, mint, size_usd, SLIPPAGE_BPS, input_decimals=9)
            if err or not quote:
                print(f"  [trader] quote failed: {err}")
                return
            result = jupiter.execute_swap(self.keypair, quote)
            if not result["success"]:
                print(f"  [trader] swap failed: {result['error']}")
                return
            print(f"  [trader] ✅ tx: https://solscan.io/tx/{result['tx']}")
            # Sync real balance after live buy
            self._sync_live_balance()
        else:
            self.balance -= size_usd

        remaining_str = format_balance(self.balance, self.sol_price)

        self.positions[mint] = {
            "name":       name,
            "mint":       mint,
            "entry":      price,
            "entry_liq":  coin.get("liquidity", 0),
            "entry_vol":  coin.get("volume_1h", 0),
            "tokens":     tokens,
            "tier1_hit":  False,
            "tier2_hit":  False,
            "size_usd":   size_usd,
            "trade_pct":  trade_pct,
            "tp":         tp,
            "sl":         sl,
            "hold_cap":   hold_cap,
            "score":      score,
            "sources":    coin.get("sources", []),
            "confidence": confidence,
            "thesis":     thesis,
            "risk":       risk,
            "opened_at":  datetime.now().isoformat(),
            "open_ts":    time.time(),
        }
        self.trades += 1
        acted_on.add(mint)
        self._save()

        # Telegram alert on buy
        try:
            import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from brothers.telegram import send
            send(f"✅ {'LIVE' if LIVE_MODE else 'PAPER'} BUY {name}\n"
                 f"Entry: ${price:.8f}\nSize: ${size_usd:.2f} ({trade_pct*100:.0f}%)\n"
                 f"TP: ${tp:.8f} | SL: ${sl:.8f}\nScore: {score} conf={confidence}")
        except: pass
        brain.remember("trader",
            f"{'LIVE' if LIVE_MODE else 'PAPER'} BUY {name} @ ${price:.8f} | "
            f"size=${size_usd:.2f}{sol_size_str} ({trade_pct*100:.0f}%) | "
            f"TP=${tp:.8f} | SL=${sl:.8f} | score={score} conf={confidence} | {thesis}",
            type="trade", tags=f"{name.lower()},buy")

        print(f"""
{GR}{BD}╔══════════════════════════════════════════════╗
║  ✅ {'LIVE' if LIVE_MODE else 'PAPER'} BUY  ▶  {name:<28}║
╠══════════════════════════════════════════════╣{RS}
  {DM}💲 Entry     {RS}  {BD}${price:.8f}{RS}
  {DM}💵 Size      {RS}  {BD}${size_usd:.2f}{sol_size_str}{RS}  ({trade_pct*100:.0f}% of balance)
  {DM}🎯 TP / SL   {RS}  {GR}${tp:.8f}{RS} / {RD}${sl:.8f}{RS}
  {DM}⭐ Score     {RS}  {YL}{BD}{score}/100{RS}  conf={confidence}/100
  {DM}💡 Thesis    {RS}  {thesis}
  {DM}⚠️  Risk      {RS}  {RD}{risk}{RS}
  {DM}💰 Balance   {RS}  {GR}{remaining_str}{RS} remaining
{GR}{BD}╚══════════════════════════════════════════════╝{RS}""")

    # ── SELL ───────────────────────────────────────────────

    def sell(self, mint, reason="manual"):
        if mint not in self.positions:
            return
        pos   = self.positions[mint]
        price = self.get_price(mint, context=f"sell {pos['name']}")
        if not price:
            print(f"  [trader] could not get price to sell {pos['name']} — holding")
            return

        if not self._price_is_sane(pos["entry"], price):
            print(f"  [trader] ⚠️  refusing to sell {pos['name']} — price looks wrong")
            return

        pnl_usd = (price - pos["entry"]) / pos["entry"] * pos["size_usd"]
        pnl_pct = (price - pos["entry"]) / pos["entry"] * 100

        if LIVE_MODE:
            quote, err = jupiter.get_quote(mint, SOL_MINT, pos["size_usd"], SLIPPAGE_BPS, input_decimals=9)
            if not err and quote:
                result = jupiter.execute_swap(self.keypair, quote)
                if result["success"]:
                    print(f"  [trader] sell tx: https://solscan.io/tx/{result['tx']}")
                    # Sync real balance after live sell
                    self._sync_live_balance()
                else:
                    print(f"  [trader] sell failed: {result['error']}")
                    return
        else:
            self.balance += pos["size_usd"] + pnl_usd

        self.total_pnl += pnl_usd
        name      = pos["name"]
        held_mins = round((time.time() - pos.get("open_ts", time.time())) / 60, 1)

        self.history.append({
            "name":      name,
            "mint":      mint,
            "entry":     pos["entry"],
            "exit":      price,
            "pnl_usd":   round(pnl_usd, 4),
            "pnl_pct":   round(pnl_pct, 2),
            "held_mins": held_mins,
            "reason":    reason,
            "score":     pos.get("score", 0),
            "sources":   pos.get("sources", []),
            "thesis":    pos.get("thesis", ""),
            "size_usd":  pos["size_usd"],
            "trade_pct": pos.get("trade_pct", MAX_TRADE_PCT),
            "ts":        datetime.now().isoformat(),
        })
        del self.positions[mint]
        self.session_trades.append(self.history[-1])
        self._save()

        emoji = "💰" if pnl_usd >= 0 else "🛑"
        # Telegram alert on sell
        try:
            import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from brothers.telegram import send
            send(f"{emoji} {'LIVE' if LIVE_MODE else 'PAPER'} SELL {name}\n"
                 f"Exit: ${price:.8f}\nPnL: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)\nReason: {reason}")
        except: pass
        brain.remember("trader",
            f"{'LIVE' if LIVE_MODE else 'PAPER'} SELL {name} @ ${price:.8f} | "
            f"PnL=${pnl_usd:+.2f} ({pnl_pct:+.1f}%) | reason={reason}",
            type="trade", tags=f"{name.lower()},sell")
        brain.learn("trader", name,
            f"entry=${pos['entry']:.8f} exit=${price:.8f} "
            f"PnL={pnl_pct:+.1f}% reason={reason} thesis={pos.get('thesis','')}")

        if pnl_usd < 0:
            loss_count[mint] = loss_count.get(mint, 0) + 1
            if loss_count[mint] >= 2:
                blacklist.add(mint)
                print(f"  [trader] 🚫 {name} added to blacklist — lost {loss_count[mint]} times")

        self._print_stats()
        pnl_color = GR if pnl_usd >= 0 else RD
        bal_str   = format_balance(self.balance, self.sol_price)
        print(f"""
{pnl_color}{BD}╔══════════════════════════════════════════════╗
║  {emoji} {'LIVE' if LIVE_MODE else 'PAPER'} SELL  ◀  {name:<27}║
╠══════════════════════════════════════════════╣{RS}
  {DM}💲 Exit      {RS}  {BD}${price:.8f}{RS}
  {DM}📊 PnL       {RS}  {pnl_color}{BD}${pnl_usd:+.2f}  ({pnl_pct:+.1f}%){RS}
  {DM}📌 Reason    {RS}  {reason}
  {DM}💰 Balance   {RS}  {GR}{bal_str}{RS}  |  Total: {pnl_color}{BD}${self.total_pnl:+.2f}{RS}
{pnl_color}{BD}╚══════════════════════════════════════════════╝{RS}""")

    # ── Position management ────────────────────────────────

    def check_positions(self):
        for mint, pos in list(self.positions.items()):
            md = self.get_market_data(mint)
            if not md:
                continue

            price     = md["price"]
            change_5m = md["change_5m"]
            change_1h = md["change_1h"]
            buys      = md["buys"]
            sells     = md["sells"]
            liq       = md["liq"]
            vol_1h    = md["vol_1h"]

            if not self._price_is_sane(pos["entry"], price):
                if price <= pos["sl"] or (price - pos["entry"]) / pos["entry"] < -0.12:
                    self.sell(mint, "stop loss (large drop, sanity override)")
                continue

            pnl_pct   = (price - pos["entry"]) / pos["entry"] * 100
            held_mins = (time.time() - pos.get("open_ts", time.time())) / 60
            buy_ratio = buys / max(1, buys + sells)

            # Track peak for trailing stop
            if price > pos.get("peak", pos["entry"]):
                pos["peak"] = price
            peak_gain = (pos.get("peak", pos["entry"]) - pos["entry"]) / pos["entry"] * 100

            # ── Tighten trailing stop as profit grows ────────
            if pnl_pct >= 10:
                new_sl = price * 0.97        # trail 3% below current at +10%
            elif pnl_pct >= 6:
                new_sl = price * 0.955       # trail 4.5% below current at +6%
            elif pnl_pct >= 3:
                new_sl = pos["entry"] * 1.01 # lock breakeven+1% at +3%
            elif pnl_pct >= 2:
                new_sl = pos["entry"] * 1.005 # tiny lock at +2%
            else:
                new_sl = pos["sl"]
            if new_sl > pos["sl"]:
                pos["sl"] = round(new_sl, 10)
                print(f"  [trader] 📈 {pos['name']} stop locked → ${pos['sl']:.8f} ({pnl_pct:+.1f}%)")

            # ── Stop hit ─────────────────────────────────────
            if price <= pos["sl"]:
                reason = (f"trailing stop +{peak_gain:.1f}% peak"
                          if peak_gain >= 2 else f"stop loss -{STOP_LOSS_PCT*100:.0f}%")
                if peak_gain < 2:
                    cooldown[mint] = {"ts": time.time(), "mins": COOLDOWN_STOP}
                self.sell(mint, reason)
                continue

            # ── Smart exit — multiple weak signals ───────────
            exit_signals = 0
            exit_reasons = []
            if change_5m < -4:
                exit_signals += 1
                exit_reasons.append(f"5m red {change_5m:+.1f}%")
            if buy_ratio < 0.45:
                exit_signals += 1
                exit_reasons.append(f"buyers {buy_ratio:.0%}")
            if change_1h < 0 and peak_gain > 3:
                exit_signals += 1
                exit_reasons.append("1h fading")
            if vol_1h < pos.get("entry_vol", vol_1h) * 0.5 and peak_gain > 3:
                exit_signals += 1
                exit_reasons.append("vol dying")
            if exit_signals >= 2 and pnl_pct > 1.5:
                self.sell(mint, f"smart exit +{pnl_pct:.1f}% [{', '.join(exit_reasons)}]")
                continue

            # ── Tier exits — lock in profits on the way up ───
            entry    = pos["entry"]
            tokens   = pos["tokens"]
            t1_price = round(entry * 1.10, 10)   # sell 33% at +10%
            t2_price = round(entry * 1.22, 10)   # sell 33% at +22%

            if not pos.get("tier1_hit") and price >= t1_price:
                sell_tokens = tokens * 0.33
                sell_value  = sell_tokens * price
                pnl_slice   = sell_value - (sell_tokens * entry)
                self.balance    += sell_value
                self.total_pnl  += pnl_slice
                pos["tier1_hit"] = True
                pos["sl"]        = round(entry * 1.01, 10)
                self._save()
                print(f"  [trader] 💰 T1 {pos['name']} sold 33% @ ${price:.8f} (+10%) "
                      f"| +${pnl_slice:.2f} | stop → breakeven+1%")
                continue

            if pos.get("tier1_hit") and not pos.get("tier2_hit") and price >= t2_price:
                sell_tokens = tokens * 0.33
                sell_value  = sell_tokens * price
                pnl_slice   = sell_value - (sell_tokens * entry)
                self.balance    += sell_value
                self.total_pnl  += pnl_slice
                pos["tier2_hit"] = True
                pos["sl"]        = round(price * 0.94, 10)
                self._save()
                print(f"  [trader] 💰 T2 {pos['name']} sold 33% @ ${price:.8f} (+22%) "
                      f"| +${pnl_slice:.2f} | trailing last 33%")
                continue

            # ── Max hold time ─────────────────────────────────
            pos_hold_cap = pos.get("hold_cap", MAX_HOLD_MINS)
            if held_mins >= pos_hold_cap:
                cooldown[mint] = {"ts": time.time(), "mins": COOLDOWN_HOLD}
                self.sell(mint, f"max hold {pos_hold_cap}min")
                continue

            # ── Liquidity collapse ────────────────────────────
            entry_liq = pos.get("entry_liq", liq)
            if liq < entry_liq * 0.5 and liq < 10_000:
                self.sell(mint, f"liquidity collapse ${liq:,.0f}")
                continue

            # ── Flat / going nowhere ──────────────────────────
            flat_exit = max(3, pos_hold_cap * 0.15)
            if held_mins >= flat_exit and -2 < pnl_pct < 2:
                cooldown[mint] = {"ts": time.time(), "mins": COOLDOWN_HOLD}
                self.sell(mint, f"flat after {int(held_mins)}min")
                continue

    # ── Signal processing ──────────────────────────────────

    def check_watchlist(self):
        watches = brain.recall(type="watch_signal", limit=30)
        for w in watches:
            try:
                sig_ts   = datetime.fromisoformat(w.get("ts", ""))
                age_secs = (datetime.now() - sig_ts).total_seconds()
                if age_secs > 600:
                    continue
                c        = w["content"]
                parts    = c.split("|")
                name     = parts[0].split("WATCH")[1].split("@")[0].strip()
                score    = int([p for p in parts if "score=" in p][0].split("=")[1].strip())
                mint     = [p for p in parts if "mint=" in p][0].split("=")[1].strip()
                age      = float([p for p in parts if "age=" in p][0].split("=")[1].replace("h","").strip())
                ch5m_sig = float([p for p in parts if "5m=" in p][0].split("=")[1].replace("%","").strip())
                if mint in self.positions or mint in acted_on:
                    continue
                if is_on_cooldown(mint):
                    continue
                if score < MIN_SCORE:
                    continue
                try:
                    fr   = requests.get(
                        f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
                        timeout=6).json()
                    fp   = [p for p in fr.get("pairs", []) if p.get("chainId") == "solana"]
                    if not fp:
                        continue
                    best = sorted(fp,
                        key=lambda x: float(x.get("liquidity",{}).get("usd",0) or 0),
                        reverse=True)[0]
                except Exception:
                    continue
                ch5m_now  = float(best.get("priceChange",{}).get("m5", 0) or 0)
                ch1h_now  = float(best.get("priceChange",{}).get("h1", 0) or 0)
                buys      = int(best.get("txns",{}).get("h1",{}).get("buys", 0) or 0)
                sells     = int(best.get("txns",{}).get("h1",{}).get("sells", 0) or 0)
                liq       = float(best.get("liquidity",{}).get("usd", 0) or 0)
                price_now = float(best.get("priceUsd", 0) or 0)
                buy_ratio = buys / max(1, buys + sells)
                was_dipping  = ch5m_sig < 0
                now_bouncing = ch5m_now > 1
                momentum_ok  = ch1h_now > 2
                buyers_ok    = buy_ratio >= 0.58
                liq_ok       = liq >= 10_000
                if not all([was_dipping, now_bouncing, momentum_ok, buyers_ok, liq_ok]):
                    print(f"  [watchlist] ⏳ {name} not ready — 5m was {ch5m_sig:+.1f}% now {ch5m_now:+.1f}% 1h={ch1h_now:+.1f}% ratio={buy_ratio:.0%}")
                    continue
                print(f"  [watchlist] 🎯 {name} BOUNCED — buying")
                coin = {
                    "name":       name,  "mint":       mint,
                    "price":      price_now, "mcap":   float(best.get("marketCap", 0) or 0),
                    "age_hrs":    age,   "liquidity":  liq,
                    "volume_24h": float(best.get("volume",{}).get("h24", 0) or 0),
                    "volume_1h":  float(best.get("volume",{}).get("h1", 0) or 0),
                    "change_1h":  ch1h_now, "change_5m": ch5m_now,
                    "buys_1h":    buys,  "sells_1h":  sells,
                }
                self.buy(coin, score, ["bounce from dip", f"5m {ch5m_now:+.1f}%", f"1h {ch1h_now:+.1f}%"])
            except Exception:
                continue

    def check_signals(self):
        signals = brain.recall(type="trade_signal", limit=20)
        for s in signals:
            c = s["content"]
            if "BUY" not in c:
                continue
            try:
                sig_ts   = datetime.fromisoformat(s.get("ts", ""))
                age_secs = (datetime.now() - sig_ts).total_seconds()
                if age_secs > 180:
                    continue
                parts   = c.split("|")
                header  = parts[0].strip()
                name    = header.split("BUY")[1].split("@")[0].strip()
                price   = float(header.split("@")[1].strip().replace("$", ""))
                score   = int([p for p in parts if "score=" in p][0].split("=")[1].strip())
                reasons = [p.strip() for p in parts[2:5] if p.strip()]
                mcap_str = [p for p in parts if "mcap=" in p]
                mcap     = float(mcap_str[0].split("=")[1].replace("$","").replace(",","").strip()) if mcap_str else 0
                age_str  = [p for p in parts if "age=" in p]
                age      = float(age_str[0].split("=")[1].replace("h","").strip()) if age_str else 999
                if score < 80:
                    continue
                if age > 48:
                    continue
                mint_parts = [p for p in parts if "mint=" in p.lower()]
                if mint_parts:
                    mint = mint_parts[0].split("=")[1].strip()
                else:
                    r     = requests.get(
                        f"https://api.dexscreener.com/latest/dex/tokens/{name}", timeout=6)
                    pairs = r.json().get("pairs", [])
                    sol   = [p for p in pairs if p.get("chainId") == "solana"
                             and p.get("baseToken",{}).get("symbol","").upper() == name.upper()]
                    if not sol:
                        continue
                    best  = sorted(sol,
                        key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0),
                        reverse=True)[0]
                    mint  = best["baseToken"]["address"]
                if mint in acted_on or mint in self.positions:
                    continue
                try:
                    fr = requests.get(
                        f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=6).json()
                    fp = [p for p in fr.get("pairs", []) if p.get("chainId") == "solana"]
                    if not fp:
                        continue
                    best = sorted(fp,
                        key=lambda x: float(x.get("liquidity",{}).get("usd",0) or 0),
                        reverse=True)[0]
                except Exception:
                    continue
                buys  = int(best.get("txns", {}).get("h1", {}).get("buys", 0) or 0)
                sells = int(best.get("txns", {}).get("h1", {}).get("sells", 0) or 0)
                liq   = float(best.get("liquidity", {}).get("usd", 0) or 0)
                vol   = float(best.get("volume", {}).get("h24", 0) or 0)
                ch1h  = float(best.get("priceChange", {}).get("h1", 0) or 0)
                ch5m  = float(best.get("priceChange", {}).get("m5", 0) or 0)
                vol1h = float(best.get("volume", {}).get("h1", 0) or 0)
                price = float(best.get("priceUsd", 0) or 0) or price
                buy_ratio = buys / max(1, buys + sells)
                if ch1h < -15 or ch1h > 800:
                    acted_on.add(mint); continue
                if buy_ratio < 0.52:
                    acted_on.add(mint); continue
                if liq < 10_000:
                    acted_on.add(mint); continue
                if ch5m < -3:
                    acted_on.add(mint); continue
                coin = {
                    "name":       name,  "mint":       mint,
                    "price":      price, "mcap":       mcap,
                    "age_hrs":    age,   "liquidity":  liq,
                    "volume_24h": vol,   "volume_1h":  vol1h,
                    "change_1h":  ch1h,  "change_5m":  ch5m,
                    "buys_1h":    buys,  "sells_1h":   sells,
                }
                self.buy(coin, score, reasons)
            except Exception:
                continue

    # ── Status ─────────────────────────────────────────────

    def print_status(self):
        now     = datetime.now().strftime("%H:%M:%S")
        bal_str = format_balance(self.balance, self.sol_price)
        print(f"\n  [{now}] {bal_str}  pnl=${self.total_pnl:+.2f}  "
              f"positions={len(self.positions)}  trades={self.trades}")
        for mint, pos in self.positions.items():
            price   = self.get_price(mint) or pos["entry"]
            pnl_pct = (price - pos["entry"]) / pos["entry"] * 100
            held    = int((time.time() - pos.get("open_ts", time.time())) / 60)
            bar     = "🟢" if pnl_pct >= 0 else "🔴"
            sane    = "" if self._price_is_sane(pos["entry"], price) else " ⚠️ price?"
            print(f"  {bar} {pos['name']:<10} entry=${pos['entry']:.8f}  "
                  f"now=${price:.8f}  {pnl_pct:+.1f}%  held={held}min"
                  f"  TP=+{TAKE_PROFIT_PCT*100:.0f}%  SL=-{STOP_LOSS_PCT*100:.0f}%{sane}")

    # ── Safety checks ──────────────────────────────────────

    def is_profit_locked(self):
        if not hasattr(self, "day_start_balance"):
            self.day_start_balance = self.balance
        target = self.day_start_balance * 1.07
        floor  = self.day_start_balance * 0.95
        if self.balance <= floor and len(self.positions) == 0:
            print(f"  [trader] 🛑 daily loss limit — down 5% today ({format_balance(self.balance, self.sol_price)})")
            return True
        if self.balance >= target and len(self.positions) == 0:
            print(f"  [trader] 🔒 profit lock — up 7% today ({format_balance(self.balance, self.sol_price)})")
            return True
        return False

    def is_market_choppy(self):
        recent = self.session_trades[-3:] if len(self.session_trades) >= 3 else []
        if len(recent) == 3 and all(t["pnl_usd"] < 0 for t in recent):
            print(f"  [trader] 📉 choppy — last 3 trades all losses, skipping this cycle")
            return True
        return False

    def is_good_trading_hour(self):
        hour = datetime.now().hour
        if hour < 8 or hour >= 20:
            print(f"  [trader] 🕐 outside trading hours — resting")
            return False
        return True

    # ── Main loop ──────────────────────────────────────────

    def run(self):
        print(f"{CY}{BD}🤖 BR0THER TRADER [{self.mode}]{RS} running — Ctrl+C to stop\n")
        cycle = 0
        while True:
            try:
                # Refresh SOL price every minute
                if cycle % 6 == 0:
                    self._refresh_sol_price()
                # Sync live wallet balance every 5 mins
                if LIVE_MODE and cycle % 30 == 0:
                    self._sync_live_balance()
                cycle += 1
                if (not self.is_profit_locked()
                        and self.is_good_trading_hour()
                        and not self.is_market_choppy()):
                    self.check_signals()
                    self.check_watchlist()
                self.check_positions()
                self.print_status()
                time.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                print("\n[trader] shutting down — saving state...")
                self._save()
                break
            except Exception as e:
                print(f"[trader] error: {e}")
                time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    Trader().run()
