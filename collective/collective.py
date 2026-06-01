"""
collective.py - BR0THA Council Voting System
Weighted votes. Profits compound. Capital protected.
"""

import asyncio
import json
import re
import sqlite3
from datetime import datetime

from ai_engine import ask_ai
from agent_personas import get_agent_list, get_persona, get_weight, COUNCIL_CONFIG
from market_data import fetch_token_data

DB_PATH = "data/agent.db"


def init_council_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS council_votes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            token      TEXT,
            agent      TEXT,
            decision   TEXT,
            confidence REAL,
            weight     INTEGER,
            timestamp  TEXT
        );
        """)


def extract_json(raw_text):
    raw = str(raw_text).strip()
    raw = re.sub(r"```json|```", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise Exception("No JSON object found")
    return json.loads(raw[start:end+1].replace("\n", " "))


# [FIX] retries once on JSON parse failure instead of voting PASS at 0%
async def run_agent(agent_name, task):
    persona = get_persona(agent_name)
    prompt = f"""You are {persona['name']}.
ROLE: {persona['role']}
SYSTEM: {persona['system']}
TASK: {task}
Return ONLY valid JSON, no markdown, no commentary.
Format: {{"agent": "{persona['name']}", "decision": "TRADE|HOLD|PASS", "confidence": 0-100, "thesis": "one sentence", "reasoning": "two sentences"}}"""

    for attempt in range(2):
        try:
            response = await asyncio.to_thread(ask_ai, prompt, agent_name, persona["system"])
            return extract_json(response)
        except Exception as e:
            if attempt == 0 and "No JSON" in str(e):
                # nudge it harder on retry
                prompt += "\n\nCRITICAL: Return ONLY the JSON object. Start with { and end with }. No other text."
                continue
            # both attempts failed — abstain rather than poison the vote
            return {
                "agent":      persona["name"],
                "decision":   "HOLD",   # HOLD = abstain, not counted as TRADE or PASS
                "confidence": 0,
                "thesis":     f"error: {e}",
                "reasoning":  "Agent failed after retry. Vote abstained."
            }


def tally_votes(results, agent_keys):
    cfg = COUNCIL_CONFIG
    total_weight = sum(get_weight(k) for k in agent_keys)
    trade_weight = 0
    trade_count = 0
    veto_fired = False
    veto_by = None

    for key, r in zip(agent_keys, results):
        w = get_weight(key)
        decision = r.get("decision", "PASS").upper()
        if decision == "TRADE":
            trade_weight += w
            trade_count += 1
        if key in cfg["veto_agents"] and decision == "PASS":
            veto_fired = True
            veto_by = r.get("agent", key)

    weighted_pct = round((trade_weight / total_weight) * 100) if total_weight else 0
    avg_conf = round(sum(r.get("confidence", 0) for r in results) / len(results)) if results else 0

    if veto_fired:
        approved = False
        reason = f"VETO by {veto_by}"
    elif trade_count < cfg["min_agents_trade"]:
        approved = False
        reason = f"only {trade_count}/{cfg['min_agents_trade']} agents voted TRADE"
    elif weighted_pct < cfg["vote_threshold"]:
        approved = False
        reason = f"weighted vote {weighted_pct}% below {cfg['vote_threshold']}% threshold"
    else:
        approved = True
        reason = f"council approved — {weighted_pct}% weighted yes"

    return {
        "approved": approved,
        "reason": reason,
        "trade_count": trade_count,
        "total_agents": len(results),
        "weighted_pct": weighted_pct,
        "avg_confidence": avg_conf,
        "veto_fired": veto_fired,
    }


def size_position(portfolio_cash, price):
    cfg = COUNCIL_CONFIG
    pos_usd = round(portfolio_cash * cfg["max_position_pct"], 2)
    return {
        "position_usd": pos_usd,
        "tokens": round(pos_usd / price, 4) if price else 0,
        "tp_price": round(price * (1 + cfg["tp_target"]), 8),
        "sl_price": round(price * (1 + cfg["sl_target"]), 8),
        "take_profit_usd": round(pos_usd * cfg["take_profit_pct"], 2),
        "moon_bag_usd": round(pos_usd * cfg["moon_bag_pct"], 2),
        "compound_usd": round(pos_usd * cfg["compound_pct"], 2),
    }


def log_votes(token, agent_keys, results):
    try:
        with sqlite3.connect(DB_PATH) as db:
            now = datetime.utcnow().isoformat()
            for key, r in zip(agent_keys, results):
                db.execute(
                    "INSERT INTO council_votes VALUES (null,?,?,?,?,?,?)",
                    (token, r.get("agent"), r.get("decision"),
                     r.get("confidence", 0), get_weight(key), now)
                )
    except Exception:
        pass


def print_council(token, results, agent_keys, verdict):
    lines = [f"\n[COUNCIL] ══════════════════════════════════ {token}"]
    total_w = sum(get_weight(k) for k in agent_keys)
    for key, r in zip(agent_keys, results):
        decision = r.get("decision", "?").upper()
        conf = r.get("confidence", 0)
        w = get_weight(key)
        thesis = str(r.get("thesis", ""))[:70]
        veto = "⚡" if key in COUNCIL_CONFIG["veto_agents"] else " "
        symbol = "✅" if decision == "TRADE" else "❌"
        lines.append(f"  {symbol} {veto}{r.get('agent','?'):10} → {decision:5} ({conf}%) [w={w}x] | {thesis}")

    lines.append(f"\n  [VOTE] {token}: {verdict['trade_count']}/{verdict['total_agents']} TRADE | weighted={verdict['weighted_pct']}% | avg conf={verdict['avg_confidence']}%")
    if verdict["approved"]:
        lines.append(f"  ✅ COUNCIL APPROVES TRADE — {verdict['reason']}")
    else:
        lines.append(f"  ❌ COUNCIL BLOCKS TRADE — {verdict['reason']}")

    print("\n".join(lines))


async def collective_debate(task, token=None, token_data=None, portfolio_cash=1000.0):
    init_council_db()

    market_context = ""
    price = 0.0
    display_token = token or "UNKNOWN"

    try:
        md = token_data if token_data else (fetch_token_data(token) if token else {})
        price = float(md.get("price") or 0)
        market_context = f"""
LIVE MARKET DATA:
Token: {md.get('token')} | Price: {md.get('price')} | 24h Vol: {md.get('volume_24h')}
Liquidity: {md.get('liquidity')} | FDV: {md.get('fdv')} | 24h Change: {md.get('price_change_24h')}
Buys 24h: {md.get('buys_24h')} | Sells 24h: {md.get('sells_24h')} | DEX: {md.get('dex')}"""
    except Exception as e:
        market_context = f"\nMarket data error: {e}"

    agent_keys = get_agent_list()
    full_task = task + market_context

    async def _run(agent, i):
        await asyncio.sleep(i * 0.3)
        return await run_agent(agent, full_task)

    results = await asyncio.gather(*[_run(a, i) for i, a in enumerate(agent_keys)])
    verdict = tally_votes(results, agent_keys)
    print_council(display_token, results, agent_keys, verdict)
    log_votes(display_token, agent_keys, results)

    sizing = None
    if verdict["approved"] and price > 0:
        sizing = size_position(portfolio_cash, price)
        print(f"  [SIZE] Risk=${sizing['position_usd']} | TP=${sizing['tp_price']} | SL=${sizing['sl_price']}")
        print(f"         At TP: take=${sizing['take_profit_usd']} | compound=${sizing['compound_usd']} | moon bag=${sizing['moon_bag_usd']}")

    return {"verdict": verdict, "results": results, "sizing": sizing, "token": display_token}


if __name__ == "__main__":
    task = input("\nEnter token or task:\n> ")
    asyncio.run(collective_debate(task))

