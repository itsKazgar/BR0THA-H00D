"""
BR0THA Multi-Model Router
Async wrapper around ai_engine.py for Telegram bot + FastAPI.
Routes messages to the best agent. Falls back through provider chain automatically.
"""

import os, asyncio, sqlite3, logging
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv("/home/kazgar/BR0THER-H00D/.env")

from ai_engine import ask_ai, RAM_GB, PROVIDERS, AGENT_PROVIDERS, provider_available
try:
    from intel_feed import build_context
    FEED_OK = True
except Exception as e:
    FEED_OK = False
    def build_context(token=None): return ""
    print(f"[FEED] intel_feed not available: {e}")

logger  = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "/home/kazgar/BR0THER-H00D/brotha.db")

# =============================================================================
# ROUTING RULES  —  keyword → agent name
# Agent names must match keys in AGENT_PROVIDERS (ai_engine.py)
# =============================================================================

ROUTING_RULES = [
    # Intel / realtime
    (["twitter","crypto twitter"," ct ","tweet","trending","kol","grok","alpha drop"],              "intel"),
    (["latest","right now","today","news","current","what happened","search","look up","happening"], "intel"),
    # Coder
    (["calculate","code","script","function","debug","error","math","solve","implement","fix"],      "coder"),
    # Quick answers
    (["quick","fast","short answer","one liner","just tell me","briefly","tldr"],                    "intel"),
    # Research
    (["summarize","read this","long doc","full context","paste","explain this"],                     "research"),
    # Market / trading
    (["market","trade","signal","buy","sell","pump","dump","chart","entry","exit","tp","sl"],        "analyst"),
    # Risk
    (["risk","stop loss","leverage","liquidation","exposure","drawdown","hedge"],                    "risk"),
    # On-chain
    (["whale","wallet","on-chain","onchain","transaction","holder","nft","token launch"],             "onchain"),
    # Yield / income
    (["yield","apy","apr","stake","lp","pool","farm","liquidity","earn"],                            "income"),
    # Security
    (["rug","scam","audit","contract","honeypot","exploit","vulnerable","unsafe"],                   "security"),
    # Orchestrator
    (["plan","council","strategy","coordinate","orchestrate","multi-step","think through"],           "orchestrator"),
]

# Direct agent aliases (used when the caller explicitly sets agent=)
_DIRECT = {
    "trader":       "trader",
    "intel":        "intel",
    "analyst":      "analyst",
    "risk":         "risk",
    "security":     "security",
    "income":       "income",
    "onchain":      "onchain",
    "coder":        "coder",
    "research":     "research",
    "orchestrator": "orchestrator",
    "default":      "default",
    "assistant":    "default",
}

def route_agent(text: str, agent_hint: str = "assistant") -> str:
    if agent_hint in _DIRECT:
        return _DIRECT[agent_hint]
    t = text.lower()
    for keywords, agent in ROUTING_RULES:
        if any(k in t for k in keywords):
            return agent
    return "default"

# =============================================================================
# SHARED BRAIN  (SQLite memory — persisted insights)
# =============================================================================

def get_shared_context(limit: int = 5) -> str:
    try:
        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute(
                "SELECT topic, insight FROM bot_learnings ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        if not rows:
            return ""
        return "\n[SHARED BRAIN]\n" + "\n".join(f"- {t}: {i}" for t, i in rows) + "\n"
    except:
        return ""

def write_shared_context(topic: str, insight: str, source: str = "model"):
    try:
        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                "INSERT INTO bot_learnings (topic,insight,confidence,source) VALUES (?,?,?,?)",
                (topic[:120], insight[:500], 0.7, source)
            )
    except:
        pass

def log_collab(user_id, prompt, model_used, response):
    try:
        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                "INSERT INTO ai_collab_log (user_id,prompt,final_response,models_used) VALUES (?,?,?,?)",
                (str(user_id), prompt[:1000], response[:2000], model_used)
            )
    except:
        pass

# =============================================================================
# ASYNC SMART ASK  —  main entry point for bot / API
# =============================================================================

_executor = ThreadPoolExecutor(max_workers=8)

async def smart_ask(
    text:            str,
    user_id          = None,
    agent:           str  = "assistant",
    system_override: str  = "",
    history:         list = None,
    max_tokens:      int  = 1024,
) -> str:
    chosen_agent = route_agent(text, agent)
    system = system_override or (
        "You are BR0THA — sharp, no-BS Solana/crypto AI. "
        "Speak directly, use a bit of slang, get to the point. Never be cringe."
    )
    system += get_shared_context()

    # Inject live market intel
    if FEED_OK:
        import re
        token_match = re.search(r'\$([A-Z]{2,10})', text.upper())
        token = token_match.group(1) if token_match else None
        live_ctx = build_context(token=token)
        if live_ctx:
            system += live_ctx

    full_prompt = text
    if history:
        ctx = "\n".join(
            f"{'User' if m['role']=='user' else 'BR0THA'}: {m['content']}"
            for m in history[-6:]
        )
        full_prompt = f"[Context]\n{ctx}\n\n[Current message]\n{text}"

    loop  = asyncio.get_event_loop()
    reply = await loop.run_in_executor(
        _executor,
        lambda: ask_ai(full_prompt, chosen_agent, system, max_tokens)
    )

    log_collab(user_id, text, chosen_agent, reply)

    if hash(text) % 5 == 0 and len(reply) > 80:
        write_shared_context(text[:60], reply[:200], source=chosen_agent)

    return reply

# =============================================================================
# COUNCIL VOTE  —  run N agents in parallel, return consensus + all opinions
# =============================================================================

async def council_vote(
    text:       str,
    agents:     list = None,
    system:     str  = None,
    max_tokens: int  = 512,
) -> dict:
    if agents is None:
        agents = ["analyst", "risk", "intel", "trader"]

    sys = system or (
        "You are one member of a crypto trading council. "
        "Give a direct BUY / SELL / HOLD verdict with a one-line reason. No fluff."
    )

    loop = asyncio.get_event_loop()

    async def ask_one(ag):
        try:
            return ag, await loop.run_in_executor(
                _executor, lambda: ask_ai(text, ag, sys, max_tokens)
            )
        except Exception as e:
            return ag, f"[{ag} failed: {e}]"

    results = dict(await asyncio.gather(*[ask_one(a) for a in agents]))

    buys  = sum(1 for r in results.values() if "BUY"  in r.upper())
    sells = sum(1 for r in results.values() if "SELL" in r.upper())
    holds = sum(1 for r in results.values() if "HOLD" in r.upper())

    if   buys  > sells and buys  > holds: verdict = "BUY"
    elif sells > buys  and sells > holds: verdict = "SELL"
    else:                                 verdict = "HOLD"

    return {"responses": results, "consensus": verdict}

# =============================================================================
# QUICK TEST  —  python multi_model_router.py
# =============================================================================

if __name__ == "__main__":
    async def _test():
        print("\n  Testing smart_ask routing...\n")
        cases = [
            ("what's the best trade right now?",          "assistant"),
            ("debug this python code for me",             "assistant"),
            ("quick yes or no: is SOL bullish today",     "assistant"),
            ("scan this contract for rugs",               "assistant"),
            ("what are the top yield farms on Solana?",   "assistant"),
        ]
        for msg, ag in cases:
            r = await smart_ask(msg, agent=ag, max_tokens=80)
            routed = route_agent(msg, ag)
            print(f"  [{routed:12}]  Q: {msg[:50]}")
            print(f"               A: {r[:80]}\n")

        print("  Testing council vote...\n")
        result = await council_vote("Should I BUY SOL at $180 right now?")
        print(f"  Consensus: {result['consensus']}")
        for ag, r in result["responses"].items():
            print(f"  {ag:12}: {r[:65]}")

    asyncio.run(_test())
