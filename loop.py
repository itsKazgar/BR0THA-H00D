"""
loop.py - BR0THA Unified Intelligence Loop

Two parallel tracks:
  FAST (every 60s): social scanner + watchlist price check
  FULL (every 5min): market scan + alpha filter + agent debate

Social alerts bypass the queue and go straight to debate.
All CA detections are fully enriched via Helius + Birdeye + SolTracker + Solana RPC.
"""

import asyncio, os, sqlite3, logging, time, requests, re
from datetime import datetime
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

load_dotenv(override=True)

from scanner import build_market
from agent_personas import get_agent_list
from collective import collective_debate
from alpha_engine import filter_market
from market_data import fetch_token_data, enrich_token
from paper_trader import open_position, check_positions, print_dashboard, init_paper_db

logging.basicConfig(
    filename="logs/brotha.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DB_PATH          = "data/agent.db"
FAST_INTERVAL    = 60
FULL_INTERVAL    = 300
MIN_AGENTS_TRADE = 4
PAPER_TRADE      = True
MIN_TOKEN_AGE_HOURS = 2.0  # [FIX 1] reject tokens younger than 2 hours

# ── SOCIAL WATCH ───────────────────────────────────────────────────────────────
WATCH_ACCOUNTS = {
    "aeyakovenko": 10,
    "rajgokal":    10,
    "blknoiz06":    9,
    "DegenSpartan": 8,
    "solana":       8,
    "JupiterExchange": 7,
    "cobie":        7,
    "inversebrah":  7,
}

NITTER_BASE = "https://nitter.net"
HEADERS     = {"User-Agent": "Mozilla/5.0"}
CA_PATTERN  = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')
SYM_PATTERN = re.compile(r'\$([A-Z]{2,10})\b')
ALPHA_WORDS = [
    "just launched","new token","early","gem","CA:","contract:",
    "stealth launch","fair launch","liquidity added","buying","accumulating"
]
IGNORE_SYMS = {"THE","AND","FOR","SOL","USD","BTC","ETH","NFT","API","SDK","RT"}

seen_tweets = set()
watchlist   = {}
debated     = set()

# ── DB ─────────────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            token          TEXT,
            decision       TEXT,
            confidence     REAL,
            agents_voted   INTEGER,
            price          TEXT,
            volume         REAL,
            score          REAL,
            rug_score      REAL,
            momentum_score REAL,
            timestamp      TEXT
        );
        CREATE TABLE IF NOT EXISTS scan_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tokens_scanned   INTEGER,
            tokens_approved  INTEGER,
            top_token        TEXT,
            timestamp        TEXT
        );
        CREATE TABLE IF NOT EXISTS social_signals (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            account   TEXT,
            symbol    TEXT,
            ca        TEXT,
            tweet     TEXT,
            score     INTEGER,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS outcomes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            token       TEXT,
            signal_ts   TEXT,
            decision    TEXT,
            entry_price TEXT,
            check_price TEXT,
            pnl_pct     REAL,
            check_ts    TEXT
        );
        """)

def log_paper_trade(token, decision, confidence, agents_voted,
                    price, volume, score, rug_score, momentum_score):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO paper_trades VALUES (NULL,?,?,?,?,?,?,?,?,?,?)",
            (token, decision, confidence, agents_voted,
             price, volume, score, rug_score, momentum_score,
             datetime.utcnow().isoformat())
        )
    print(f"  [PAPER] {decision} {token} @ ${price} | "
          f"agents={agents_voted} conf={confidence}%")

def log_social_signal(account, symbol, ca, tweet, score):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO social_signals VALUES (NULL,?,?,?,?,?,?)",
            (account, symbol, ca, tweet[:300], score,
             datetime.utcnow().isoformat())
        )

# ── [FIX 1] TOKEN AGE CHECK ────────────────────────────────────────────────────
def get_token_age_hours(mint: str) -> float:
    """Return token age in hours. Returns 999 on error so unknown = safe default."""
    if not mint:
        return 999.0
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
            headers=HEADERS, timeout=8
        )
        pairs = r.json().get("pairs") or []
        if not pairs:
            return 999.0
        times = [p.get("pairCreatedAt", 0) for p in pairs if p.get("pairCreatedAt")]
        if not times:
            return 999.0
        age_hours = (time.time() - min(times) / 1000) / 3600
        return round(age_hours, 2)
    except:
        return 999.0

# ── [FIX 2] FEAR & GREED ───────────────────────────────────────────────────────
_fg_cache = {"value": None, "label": None, "fetched_at": 0}

def get_fear_and_greed():
    """Free Fear & Greed index. No API key. Cached 10 min."""
    if _fg_cache["value"] and time.time() - _fg_cache["fetched_at"] < 600:
        return _fg_cache.copy()
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        d = r.json()["data"][0]
        _fg_cache.update({"value": int(d["value"]), "label": d["value_classification"], "fetched_at": time.time()})
    except:
        _fg_cache.update({"value": 50, "label": "Neutral", "fetched_at": time.time()})
    return _fg_cache.copy()

# ── SOCIAL SCANNER ─────────────────────────────────────────────────────────────
def fetch_feed(account):
    try:
        r = requests.get(f"{NITTER_BASE}/{account}/rss",
                         headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        root  = ET.fromstring(r.text)
        items = []
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            desc  = item.find("description").text or ""
            link  = item.find("link").text or ""
            date  = item.find("pubDate").text or ""
            items.append({
                "account": account,
                "text":    (title + " " + desc).strip(),
                "title":   title,
                "link":    link,
                "date":    date,
            })
        return items
    except:
        return []

def parse_tweet(tweet, weight):
    text    = tweet["text"]
    text_up = text.upper()
    score   = 0
    signals = []

    cas     = [c for c in CA_PATTERN.findall(text) if 32 <= len(c) <= 44]
    symbols = [s for s in SYM_PATTERN.findall(text_up) if s not in IGNORE_SYMS]
    keywords= [kw for kw in ALPHA_WORDS if kw in text.lower()]
    is_rt   = text.startswith("RT by")

    if cas:     score += 40 * weight; signals.append(f"CA: {cas[0][:8]}...")
    if symbols: score += 20 * weight; signals.append(f"Symbols: {', '.join(['$'+s for s in symbols[:3]])}")
    if keywords:score += 15 * weight; signals.append(f"Keywords: {', '.join(keywords[:2])}")
    if not is_rt: score += 10 * weight

    if score < 30:
        return None

    return {
        "account": tweet["account"],
        "weight":  weight,
        "score":   score,
        "signals": signals,
        "cas":     cas,
        "symbols": symbols,
        "text":    tweet["title"][:200],
        "link":    tweet["link"],
        "is_rt":   is_rt,
    }

def run_social_scan():
    priority = []
    for account, weight in WATCH_ACCOUNTS.items():
        for tweet in fetch_feed(account):
            tid = tweet["link"]
            if tid in seen_tweets:
                continue
            seen_tweets.add(tid)
            sig = parse_tweet(tweet, weight)
            if not sig:
                continue

            print(f"  [SOCIAL] @{account} (w={weight}) | {' | '.join(sig['signals'])}")
            print(f"           {sig['text'][:120]}")

            sym = sig["symbols"][0] if sig["symbols"] else ""
            ca  = sig["cas"][0]     if sig["cas"]     else ""
            log_social_signal(account, sym, ca, sig["text"], sig["score"])

            if ca:
                print(f"  [SOCIAL] ⚡ CA DETECTED: {ca}")
                priority.append({
                    "token":  sym or ca[:8],
                    "mint":   ca,
                    "source": f"social/@{account}",
                    "score":  sig["score"],
                    "weight": weight,
                    "social": sig,
                })
            elif sym:
                priority.append({
                    "token":  sym,
                    "mint":   "",
                    "source": f"social/@{account}",
                    "score":  sig["score"],
                    "weight": weight,
                    "social": sig,
                })

        time.sleep(0.4)

    return sorted(priority, key=lambda x: x["score"], reverse=True)

# ── WATCHLIST ──────────────────────────────────────────────────────────────────
def update_watchlist(tokens):
    for t in tokens:
        sym = t["token"]
        if sym not in watchlist:
            watchlist[sym] = {
                "price":      t.get("price", 0),
                "mint":       t.get("mint", ""),
                "first_seen": datetime.utcnow().isoformat(),
                "score":      t.get("score", 0),
                "rug_score":  t.get("rug_score", 0),
            }

def check_watchlist():
    alerts = []
    for sym, data in list(watchlist.items()):
        try:
            mint = data.get("mint", "")
            live = enrich_token(sym, mint) if mint else fetch_token_data(sym)
            if live.get("error"):
                continue
            new_price = float(live.get("price") or 0)
            old_price = float(data.get("price") or 0)
            if old_price <= 0 or new_price <= 0:
                continue
            change_pct = ((new_price - old_price) / old_price) * 100
            watchlist[sym]["price"] = new_price

            if abs(change_pct) >= 15:
                alerts.append({
                    "token":      sym,
                    "change_pct": change_pct,
                    "new_price":  new_price,
                    "live_data":  live,
                })
                direction = "🚀" if change_pct > 0 else "📉"
                print(f"  [WATCH] {direction} {sym} moved {change_pct:+.1f}% since first seen")
        except:
            continue
    return alerts

# ── DEBATE ─────────────────────────────────────────────────────────────────────
def build_prompt(signal):
    token   = signal["token"]
    md      = signal.get("market_data", signal)
    thesis  = signal.get("thesis", {})
    stats   = thesis.get("key_stats", {})
    bull    = thesis.get("bull_case", [])
    bear    = thesis.get("bear_case", [])
    summary = thesis.get("summary", "")
    signals = signal.get("signals", [])
    plan    = thesis.get("trade_plan", "")
    social  = signal.get("social", {})

    security      = md.get("security", {})
    concentration = md.get("concentration", {})
    soltracker    = md.get("soltracker", {})
    helius        = md.get("helius", {})

    social_block = ""
    if social:
        social_block = f"""
SOCIAL ALPHA:
  Source: @{social.get('account','')} (influence weight={social.get('weight',0)}/10)
  Tweet: {social.get('text','')[:150]}
  Signals: {', '.join(social.get('signals',[]))}
"""

    security_block = ""
    if security:
        security_block = f"""
ON-CHAIN SECURITY (Birdeye):
  Mint Authority Disabled: {security.get('mint_authority_disabled', '?')}
  Freeze Authority Disabled: {security.get('freeze_authority_disabled', '?')}
  Top 10 Holders: {security.get('top10_holder_pct', '?')}%
  LP Locked: {security.get('lp_locked_pct', '?')}%
"""

    concentration_block = ""
    if concentration:
        concentration_block = f"""
HOLDER CONCENTRATION (Solana RPC):
  Top 10 Wallets: {concentration.get('top10_pct', '?')}% of supply
  Top 1 Wallet:   {concentration.get('top1_pct', '?')}% of supply
  Concentration Risk: {concentration.get('concentration_risk', '?')}
"""

    soltracker_block = ""
    if soltracker:
        risks = soltracker.get("risks", [])
        risk_str = ", ".join([r.get("name","") if isinstance(r,dict) else str(r) for r in risks[:3]]) or "none"
        soltracker_block = f"""
SOLANA TRACKER:
  Holders: {soltracker.get('holder_count', '?')}
  LP Burned: {soltracker.get('lp_burned', '?')}%
  Risk Flags: {risk_str}
"""

    # [FIX 2] Fear & Greed block
    fg = signal.get("fear_greed", {})
    fg_block = ""
    if fg.get("value") is not None:
        v = fg["value"]
        if v <= 25:   note = "Extreme Fear — market fragile, size down"
        elif v <= 45: note = "Fear — be cautious"
        elif v <= 55: note = "Neutral — trade normally"
        elif v <= 75: note = "Greed — watch for reversals"
        else:         note = "Extreme Greed — tighten SL, take profits faster"
        fg_block = f"""
MACRO SENTIMENT:
  Fear & Greed: {v}/100 ({fg.get('label','')}) — {note}
"""

    return f"""DEBATE: Should BR0THA trade {token}?

{social_block}{fg_block}
ALPHA ENGINE:
{summary}

KEY STATS:
- Price:        {stats.get('price', md.get('price','?'))}
- 24h Change:   {stats.get('change_24h', str(md.get('change_24h','?')) + '%')}
- Volume:       {stats.get('volume', '$' + str(md.get('volume',0)))}
- Liquidity:    {stats.get('liquidity', '$' + str(md.get('liquidity',0)))}
- Buy Pressure: {stats.get('buy_pressure', str(md.get('buy_pressure','?')) + 'x')}
- Rug Score:    {stats.get('rug_score', str(signal.get('rug_score',0)) + '/100')}
- Momentum:     {stats.get('momentum', str(signal.get('momentum_score',0)) + '/100')}
- Holders:      {stats.get('holders', '?')}
- Mint Safe:    {stats.get('mint_safe', '?')}
- LP Burned:    {stats.get('lp_burned', '?')}

{security_block}
{concentration_block}
{soltracker_block}

MOMENTUM SIGNALS:
{chr(10).join('  + ' + s for s in signals) if signals else '  none'}

BULL CASE:
{chr(10).join('  + ' + b for b in bull) if bull else '  none'}

BEAR CASE:
{chr(10).join('  - ' + b for b in bear) if bear else '  none'}

TRADE PLAN: {plan}

Vote TRADE or PASS. Reference specific numbers. No generic takes."""


def get_portfolio_cash():
    try:
        from paper_trader import get_cash
        return get_cash()
    except Exception:
        return 1000.0

async def debate_token(signal):
    token = signal["token"]
    if token in debated:
        return
    debated.add(token)

    md   = signal.get("market_data", signal)
    fg   = get_fear_and_greed()        # [FIX 2] fetch macro context
    cash = get_portfolio_cash()        # [FIX 3] real cash not hardcoded
    signal["fear_greed"] = fg

    prompt = build_prompt(signal)

    try:
        result = await collective_debate(
            task=prompt,
            token=token,
            token_data=md,
            portfolio_cash=cash        # [FIX 3] was hardcoded 1000.0
        )
    except Exception as e:
        print(f"  [ERROR] Council failed: {e}")
        return

    verdict = result["verdict"]

    if verdict["approved"]:
        print(f"\n  [SIGNAL] 🚨 TRADE {token} — {verdict['trade_count']} agents, conf={verdict['avg_confidence']}%")
        log.info(f"TRADE SIGNAL: {token} votes={verdict['trade_count']} conf={verdict['avg_confidence']}")
        if PAPER_TRADE:
            open_position(
                token=token,
                mint=md.get("mint", ""),
                price=md.get("price", 0),
                agents_voted=verdict["trade_count"],
                confidence=verdict["avg_confidence"]
            )
    else:
        print(f"  [PASS] {token} — {verdict['reason']}")

# ── FAST CYCLE ─────────────────────────────────────────────────────────────────
async def fast_cycle():
    now = datetime.utcnow().strftime("%H:%M:%S")
    print(f"\n[{now}] ⚡ FAST SCAN — social + watchlist")

    priority = run_social_scan()
    if priority:
        print(f"  [SOCIAL] {len(priority)} priority tokens from CT")
        for p in priority[:2]:
            print(f"\n  [SOCIAL DEBATE] {p['token']} from @{p['source']}")
            mint = p.get("mint", "")

            if mint:
                print(f"  [ENRICH] Running full enrichment on {p['token']} ({mint[:12]}...)")
                enriched = enrich_token(p["token"], mint)
            else:
                enriched = fetch_token_data(p["token"])

            if not enriched.get("error"):
                from alpha_engine import check_rug_risk, get_momentum_signal, build_thesis
                rug      = check_rug_risk(p["token"], enriched)
                momentum = get_momentum_signal(enriched)
                thesis   = build_thesis(p["token"], enriched, rug, momentum)

                p["market_data"]    = enriched
                p["rug_score"]      = rug["risk_score"]
                p["momentum_score"] = momentum["momentum_score"]
                p["signals"]        = momentum["signals"]
                p["thesis"]         = thesis

                # [FIX 1] token age filter
                age_hours = get_token_age_hours(mint) if mint else 999.0
                print(f"  [ENRICH] age={age_hours:.1f}h | rug={rug['risk_score']}/100 | "
                      f"momentum={momentum['momentum_score']}/100 | "
                      f"mint_safe={enriched.get('mint_authority_disabled','?')} | "
                      f"holders={enriched.get('holder_count','?')}")

                if age_hours < MIN_TOKEN_AGE_HOURS:
                    print(f"  [REJECT] {p['token']} too new: {age_hours:.1f}h (min={MIN_TOKEN_AGE_HOURS}h)")
                    continue

                if rug["safe"]:
                    await debate_token(p)
                else:
                    print(f"  [REJECT] {p['token']} failed rug check: "
                          f"{'; '.join(rug['reasons'][:2])}")

    check_positions()

    alerts = check_watchlist()
    for alert in alerts:
        print(f"\n  [WATCHLIST ALERT] {alert['token']} {alert['change_pct']:+.1f}%")
        live = alert["live_data"]
        from alpha_engine import check_rug_risk, get_momentum_signal, build_thesis
        rug      = check_rug_risk(alert["token"], live)
        momentum = get_momentum_signal(live)
        thesis   = build_thesis(alert["token"], live, rug, momentum)
        sig = {
            "token":          alert["token"],
            "market_data":    live,
            "rug_score":      rug["risk_score"],
            "momentum_score": momentum["momentum_score"],
            "signals":        momentum["signals"] + [f"Price moved {alert['change_pct']:+.1f}%"],
            "thesis":         thesis,
        }
        if rug["safe"]:
            await debate_token(sig)

# ── FULL CYCLE ─────────────────────────────────────────────────────────────────
async def full_cycle():
    now = datetime.utcnow().strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[{now}] 🔭 FULL SCAN — market wide")
    print(f"{'='*60}")

    try:
        market = build_market()
    except Exception as e:
        print(f"[SCAN ERROR] {e}")
        return

    if not market:
        print("[SCAN] No tokens found.")
        return

    print(f"[SCAN] {len(market)} tokens — filtering...\n")

    enriched_market = []
    for token in market:
        mint = token.get("mint", "")
        if mint and len(mint) > 30:
            try:
                enriched = enrich_token(token["token"], mint)
                sym = token["token"]
                token.update({k: v for k, v in enriched.items() if v})
                token["token"] = sym
            except:
                pass
        enriched_market.append(token)

    approved, watching, rejected = filter_market(enriched_market)

    # [FIX 1] age filter on full scan too
    age_filtered = []
    for t in approved:
        age = get_token_age_hours(t.get("mint", ""))
        if age < MIN_TOKEN_AGE_HOURS:
            print(f"  [REJECT] {t['token']} too new: {age:.1f}h (min={MIN_TOKEN_AGE_HOURS}h)")
        else:
            age_filtered.append(t)
    approved = age_filtered

    print(f"\n[ALPHA] {len(approved)} approved | {len(watching)} watching | {len(rejected)} rejected")

    update_watchlist(watching)

    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO scan_log VALUES (NULL,?,?,?,?)",
            (len(market), len(approved),
             approved[0]["token"] if approved else "none",
             datetime.utcnow().isoformat()))

    if not approved:
        print("[ALPHA] Nothing passed filters. Watching the market...")
        return

    for signal in approved[:3]:
        print(f"\n[DEBATE] {'='*40}")
        print(f"[DEBATE] {signal['token']} | rug={signal['rug_score']}/100 | "
              f"momentum={signal['momentum_score']}/100")
        await debate_token(signal)
        await asyncio.sleep(15)

# ── MAIN ───────────────────────────────────────────────────────────────────────
async def main():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║   BR0THA COLLECTIVE — UNIFIED INTELLIGENCE  ║")
    print("║   Helius + Birdeye + SolTracker + Solana RPC║")
    print("╚════════════════════════════════════════════╝")
    init_db()
    init_paper_db()

    # [FIX 2] show Fear & Greed on startup
    fg = get_fear_and_greed()
    print(f"  [MACRO] Fear & Greed: {fg.get('value','?')}/100 ({fg.get('label','?')})")

    last_full = 0
    cycle     = 0

    while True:
        cycle += 1
        now = time.time()

        try:
            await fast_cycle()
        except Exception as e:
            print(f"[FAST ERROR] {e}")
            log.error(f"Fast cycle error: {e}")

        if now - last_full >= FULL_INTERVAL:
            try:
                await full_cycle()
                last_full = time.time()
            except Exception as e:
                print(f"[FULL ERROR] {e}")
                log.error(f"Full cycle error: {e}")

        # [FIX 4] clear debated cache every 2hrs so tokens get re-evaluated
        if cycle % 120 == 0:
            debated.clear()
            print("[SYSTEM] Debated cache cleared — tokens eligible for re-evaluation")

        print(f"\n[SLEEP] Next fast scan in 60s... "
              f"(full scan in {int(FULL_INTERVAL - (time.time() - last_full))}s)")
        await asyncio.sleep(FAST_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
