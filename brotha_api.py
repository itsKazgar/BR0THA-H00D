"""
brotha_api.py — BR0THA Dashboard API Server
Fixed: duplicate routes, /status shape, POST /votes, POST /keys, /env/update

Run: uvicorn brotha_api:app --host 0.0.0.0 --port 8000 --reload
"""

import os, sys, sqlite3, json, time, subprocess, random
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent
sys.path.insert(0, str(BOT_DIR))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from emergency_agent import install_emergency_handler
from dotenv import load_dotenv

load_dotenv(BOT_DIR / ".env", override=True)
install_emergency_handler()

# ── lazy imports ───────────────────────────────────────────────────────────────
try:
    from agent_personas import COUNCIL_CONFIG, PERSONAS
    PERSONAS_OK = True
except Exception as e:
    PERSONAS_OK = False
    PERSONAS = {}
    COUNCIL_CONFIG = {}
    print(f"[WARN] agent_personas: {e}")

try:
    from paper_trader import get_portfolio, get_open_positions, init_paper_db
    PAPER_OK = True
except Exception as e:
    PAPER_OK = False
    print(f"[WARN] paper_trader: {e}")

DB_PATH  = BOT_DIR / "data" / "agent.db"
ENV_PATH = BOT_DIR / ".env"

app = FastAPI(title="BR0THA API", version="2.0")

@app.get("/")
def dashboard():
    return FileResponse("brotha_dashboard.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_bot_process = None

# ── helpers ────────────────────────────────────────────────────────────────────

def db():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def write_env_key(key: str, value: str):
    lines = []
    found = False
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")

def fear_and_greed() -> dict:
    import httpx
    try:
        r = httpx.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except:
        return {"value": 50, "label": "Neutral"}

def bot_running() -> bool:
    global _bot_process
    if _bot_process and _bot_process.poll() is None:
        return True
    try:
        import psutil
        for proc in psutil.process_iter(["cmdline"]):
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "loop.py" in cmdline or "telegram_bot.py" in cmdline or "start.py" in cmdline or "trader.py" in cmdline:
                return True
    except:
        pass
    return False

# ── startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    os.makedirs(BOT_DIR / "data", exist_ok=True)
    if PAPER_OK:
        try:
            init_paper_db()
        except:
            pass
    print("BR0THA API v2 running — http://0.0.0.0:8000")
    print("Docs → http://localhost:8000/docs")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STATUS  —  dashboard reads: trades, version, positions[]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/status")
def get_status():
    fg = fear_and_greed()
    positions = []
    trade_count = 0
    balance = 100.0
    total_pnl = 0.0
    try:
        import sqlite3, json as _json
        _db = sqlite3.connect("core/brain.db")
        _row = _db.execute("SELECT data FROM state WHERE agent='trader'").fetchone()
        _db.close()
        if _row:
            _data = _json.loads(_row[0])
            balance = round(_data.get("balance", 100.0), 2)
            total_pnl = round(_data.get("total_pnl", 0.0), 2)
            trade_count = _data.get("trades", 0)
            for _mint, _pos in _data.get("positions", {}).items():
                positions.append({
                    "symbol":   _pos.get("name", _mint[:8]),
                    "strategy": "scalp" if _pos.get("hold_cap", 120) <= 20 else "swing",
                    "amount":   round(_pos.get("size_usd", 0), 2),
                    "pnl":      round(_pos.get("pnl_usd", 0), 2),
                    "status":   "open",
                })
    except Exception as _e:
        print(f"[status] error: {_e}")
    return {
        "trades":        trade_count,
        "version":       "2.0",
        "positions":     positions,
        "balance":       balance,
        "total_pnl":     total_pnl,
        "running":       bot_running(),
        "fear_greed":    fg["value"],
        "fg_label":      fg["label"],
        "paper_trading": True,
        "ts":            datetime.utcnow().isoformat(),
    }

@app.get("/votes")
def get_vote_log(limit: int = 20):
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT token, agent, decision, confidence, weight, timestamp "
                "FROM council_votes ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {"token": r[0], "agent": r[1], "decision": r[2],
             "confidence": r[3], "weight": r[4], "ts": r[5]}
            for r in rows
        ]
    except:
        return []


class VoteRequest(BaseModel):
    agents: list
    user_id: str = "dashboard"
    token: Optional[str] = None

@app.post("/votes")
async def run_council_vote(req: VoteRequest):
    """
    Dashboard POSTs here to trigger a live council vote.
    Tries ai_engine / multi_model_router if available,
    falls back to a clean weighted simulation.
    """
    agents = req.agents
    if not agents:
        raise HTTPException(400, "no agents provided")

    # ── try real AI vote ───────────────────────────────────────────────────
    try:
        from multi_model_router import council_vote, tally_votes
        token = req.token or "SOL"
        raw_votes = await council_vote(agents, token)
        result    = tally_votes(raw_votes, agents)
        return result
    except Exception as e:
        print(f"[votes] real vote failed ({e}), using weighted sim")

    # ── weighted simulation fallback ───────────────────────────────────────
    thesis_bias = {
        "momentum":    0.65,
        "dip_buy":     0.60,
        "breakout":    0.70,
        "whale_follow":0.58,
        "ai":          0.62,
    }

    votes = []
    for a in agents:
        bias    = thesis_bias.get(a.get("thesis", "ai"), 0.60)
        rnd     = random.random()
        decision = "buy" if rnd < bias else ("hold" if rnd < bias + 0.25 else "sell")
        conf    = random.randint(52, 94)
        votes.append({
            "agent":      a.get("name", "agent"),
            "provider":   a.get("provider", "sim"),
            "decision":   decision,
            "confidence": conf,
            "weight":     a.get("weight", 1),
            "reasoning":  f"{decision.title()} signal — {conf}% confidence based on {a.get('thesis','ai')} thesis.",
        })

    total_w  = sum(v["weight"] for v in votes)
    buy_w    = sum(v["weight"] for v in votes if v["decision"] == "buy")
    buy_pct  = round(buy_w / max(total_w, 1) * 100)
    threshold = agents[0].get("threshold", 60) if agents else 60
    decision  = "BUY" if buy_pct >= threshold else "HOLD"

    return {
        "votes":     votes,
        "buy_pct":   buy_pct,
        "decision":  decision,
        "simulated": True,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WALLET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/wallet/{address}")
async def wallet_balance(address: str):
    import httpx
    helius_key = os.getenv("HELIUS_API_KEY", "")
    rpc = f"https://mainnet.helius-rpc.com/?api-key={helius_key}" if helius_key \
          else "https://api.mainnet-beta.solana.com"
    try:
        r = httpx.post(
            rpc,
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]},
            timeout=10,
        )
        bal = r.json()["result"]["value"] / 1e9
    except:
        bal = 0.0
    return {"address": address, "sol": round(bal, 6)}

@app.post("/wallet/create")
def wallet_create():
    try:
        from solders.keypair import Keypair
        from base58 import b58encode
        kp = Keypair()
        return {
            "address":         str(kp.pubkey()),
            "private_key_b58": b58encode(bytes(kp)).decode(),
            "warning":         "Save your private key NOW — it is never shown again.",
        }
    except ImportError:
        raise HTTPException(503, "Run: pip install solders base58")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TRADE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SwapRequest(BaseModel):
    user_id:    str   = "dashboard"
    from_token: str   = "SOL"
    to_token:   str
    amount_sol: float

@app.post("/trade/swap")
async def trade_swap(req: SwapRequest):
    try:
        from trading import jupiter_swap
        return await jupiter_swap(req.user_id, req.from_token, req.to_token, req.amount_sol)
    except ImportError:
        return {"ok": False, "error": "trading.py not available — is it in ~/BR0THER-H00D/?"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/trade/history")
def trade_history(user_id: str = "dashboard", limit: int = 20):
    try:
        import sqlite3, json
        brain_db = sqlite3.connect("core/brain.db")
        row = brain_db.execute("SELECT data FROM state WHERE agent='trader'").fetchone()
        brain_db.close()
        if not row:
            return {"history": []}
        data = json.loads(row[0])
        history = data.get("history", [])[-limit:][::-1]
        return {"history": [
            {
                "symbol": t.get("name", "?"),
                "action": "SELL",
                "amount": round(t.get("size_usd", 0), 2),
                "price":  round(t.get("exit", 0), 8),
                "pnl":    round(t.get("pnl_usd", 0), 4),
                "reason": t.get("reason", ""),
                "ts":     t.get("ts", "")
            }
            for t in history
        ]}
    except Exception as e:
        return {"history": [], "note": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOKEN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/token/{query}")
def token_lookup(query: str):
    import httpx, urllib.parse
    try:
        r = httpx.get(
            f"https://api.dexscreener.com/latest/dex/search/?q={urllib.parse.quote(query)}",
            timeout=10,
        )
        pairs = [p for p in r.json().get("pairs", []) if p.get("chainId") == "solana"]
        if not pairs:
            return {"ok": False, "error": "not found on Solana"}
        best = sorted(
            pairs,
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
            reverse=True,
        )[0]
        return {
            "ok":     True,
            "mint":   best["baseToken"]["address"],
            "symbol": best["baseToken"]["symbol"],
            "name":   best["baseToken"]["name"],
            "price":  float(best.get("priceUsd") or 0),
            "mcap":   float(best.get("fdv") or 0),
            "liq":    float(best.get("liquidity", {}).get("usd") or 0),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MARKET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/market/{mtype}")
def market_data(mtype: str):
    import httpx
    try:
        if mtype == "sol":
            r = httpx.get(
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=solana,bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true",
                timeout=10,
            )
            d = r.json()
            return {"text": (
                f"SOL  ${d['solana']['usd']:.2f}  ({d['solana']['usd_24h_change']:+.1f}%)\n"
                f"BTC  ${d['bitcoin']['usd']:,.0f}  ({d['bitcoin']['usd_24h_change']:+.1f}%)\n"
                f"ETH  ${d['ethereum']['usd']:,.0f}  ({d['ethereum']['usd_24h_change']:+.1f}%)"
            )}

        elif mtype == "trending":
            r = httpx.get("https://api.coingecko.com/api/v3/search/trending", timeout=10)
            coins = r.json().get("coins", [])[:8]
            lines = ["# coingecko trending\n"]
            for i, c in enumerate(coins, 1):
                item = c["item"]
                lines.append(f"{i:2}.  {item['symbol']:<10} {item['name']}")
            return {"text": "\n".join(lines)}

        elif mtype == "pump":
            try:
                from market_data import get_pumpfun_new
                coins = get_pumpfun_new(10)
                lines = ["# pump.fun — latest\n"]
                for c in coins[:8]:
                    lines.append(
                        f"{'👑' if c.get('king_of_hill') else '•'} "
                        f"{c['symbol']:<10} ${c['mcap']:>10,.0f}"
                    )
                return {"text": "\n".join(lines)}
            except:
                return {"text": "market_data.py not available"}

        elif mtype == "grad":
            try:
                from market_data import get_pumpfun_graduating
                coins = get_pumpfun_graduating()
                lines = ["# near graduation → raydium\n"]
                for c in coins:
                    lines.append(
                        f"🚀 {c['symbol']:<10} {c['pct_to_grad']:.1f}% away  ${c['mcap']:,.0f}"
                    )
                return {"text": "\n".join(lines)}
            except:
                return {"text": "market_data.py not available"}

        else:
            return {"text": f"unknown type: {mtype}"}

    except Exception as e:
        return {"text": f"error: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AGENTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NewAgent(BaseModel):
    id:        str
    name:      str
    provider:  str  = "custom"
    model:     str
    thesis:    str  = "ai"
    size:      float = 0.05
    weight:    int  = 1
    threshold: int  = 60
    active:    bool = True

@app.get("/agents")
def get_agents():
    if not PERSONAS_OK:
        return {"agents": [], "config": {}}
    agents = []
    for key, persona in PERSONAS.items():
        if key == "orchestrator":
            continue
        agents.append({
            "id":     key,
            "name":   persona.get("name", key),
            "model":  persona.get("model", ""),
            "role":   persona.get("role", ""),
            "weight": COUNCIL_CONFIG.get("weights", {}).get(key, 1),
            "active": True,
        })
    return {"agents": agents, "config": COUNCIL_CONFIG}

@app.post("/agents")
def add_agent(body: NewAgent):
    if PERSONAS_OK:
        PERSONAS[body.id] = {
            "model":    body.model,
            "name":     body.name,
            "role":     body.thesis,
            "provider": body.provider,
            "system":   f"You are {body.name}, a trading council agent. Thesis: {body.thesis}. Be concise.",
        }
        COUNCIL_CONFIG.setdefault("weights", {})[body.id] = body.weight
    return {"ok": True, "agent": body.id}

@app.delete("/agents/{agent_id}")
def remove_agent(agent_id: str):
    if PERSONAS_OK:
        PERSONAS.pop(agent_id, None)
        COUNCIL_CONFIG.get("weights", {}).pop(agent_id, None)
    return {"ok": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  API KEYS  —  dashboard sends flat dict of ALL keys at once
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRACKED_KEYS = {
    # AI providers (dashboard key tab)
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROK_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "CEREBRAS_API_KEY",
    # infra
    "HELIUS_API_KEY",
    "BIRDEYE_API_KEY",
    "SOLTRACKER_API_KEY",
    "TELEGRAM_TOKEN",
    # wallet (stored in .env only, never logged)
    "WALLET_PRIVATE_KEY_B58",
}

def get_all_keys():
    """Returns TRACKED_KEYS plus any custom keys saved in .env"""
    custom = set()
    try:
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=")[0].strip()
                    if key not in TRACKED_KEYS:
                        custom.add(key)
    except:
        pass
    return TRACKED_KEYS | custom

@app.get("/keys")
def get_keys():
    result = {}
    for k in sorted(TRACKED_KEYS):
        val = os.getenv(k, "")
        result[k] = {"set": bool(val), "preview": (val[:4] + "****") if val else ""}
    return result

@app.post("/keys")
def save_keys(body: dict):
    """Accept flat dict  {KEY_NAME: value, ...}  — matches what dashboard sends."""
    updated = []
    for k, v in body.items():
        if not v:
            continue
        write_env_key(k, v)
        os.environ[k] = v
        updated.append(k)
    load_dotenv(ENV_PATH, override=True)
    return {"ok": True, "updated": updated}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENV UPDATE  (legacy endpoint — dashboard tries /keys first, then this)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/env/update")
def env_update(body: dict):
    """Same as POST /keys — kept for backward compat."""
    updated = []
    for k, v in body.items():
        if not v:
            continue
        write_env_key(k, v)
        os.environ[k] = v
        updated.append(k)
    load_dotenv(ENV_PATH, override=True)
    return {"ok": True, "updated": updated}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WHALE SCAN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/whale/scan")
def whale_scan():
    try:
        from trading import scan_whale_activity
        activity = scan_whale_activity()
        lines = ["# whale activity\n"]
        for w in activity:
            lines.append(
                f"{w['wallet'][:8]}…  "
                f"{w['sol_balance']:.2f} SOL  "
                f"{w['recent_txns']} recent txns"
            )
        return {"text": "\n".join(lines)}
    except Exception as e:
        return {"text": f"whale scanner unavailable: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ROBOT CONTROL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RobotRequest(BaseModel):
    user_id:  str = "dashboard"
    robot_id: str

@app.post("/robot/activate")
def robot_activate(req: RobotRequest):
    try:
        from trading import activate_robot
        ok = activate_robot(req.user_id, req.robot_id)
        return {"ok": ok, "robot": req.robot_id, "action": "activated"}
    except ImportError:
        return {"ok": False, "error": "trading.py not available"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/agents/custom")
def get_custom_agents():
    try:
        import sqlite3
        db = sqlite3.connect("core/brain.db")
        rows = db.execute("SELECT id, name, task, enabled, created_at FROM custom_agents ORDER BY id").fetchall()
        db.close()
        return {"agents": [{"id": r[0], "name": r[1], "task": r[2], "enabled": bool(r[3]), "created_at": r[4]} for r in rows]}
    except Exception as e:
        return {"agents": [], "error": str(e)}

@app.post("/agents/custom")
def save_custom_agent(body: dict):
    try:
        import sqlite3
        from datetime import datetime
        name = body.get("name", "").strip()
        task = body.get("task", "").strip()
        if not name or not task:
            raise HTTPException(status_code=400, detail="name and task required")
        db = sqlite3.connect("core/brain.db")
        db.execute("""
            INSERT INTO custom_agents (name, task, enabled, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET task=excluded.task, updated_at=excluded.updated_at
        """, (name, task, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
        db.commit()
        db.close()
        return {"ok": True, "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agents/custom/code")
def save_custom_agent_code(body: dict):
    """Save custom Python agent code to agents/trading/custom_<name>.py"""
    name = body.get("name", "").strip().replace(" ", "_").lower()
    code = body.get("code", "").strip()
    if not name or not code:
        raise HTTPException(status_code=400, detail="name and code required")
    # Basic safety check — no imports of dangerous modules
    blocked = ["os.system", "subprocess", "shutil.rmtree", "__import__('os')"]
    for b in blocked:
        if b in code:
            raise HTTPException(status_code=400, detail=f"blocked: {b}")
    path = f"agents/trading/custom_{name}.py"
    try:
        with open(path, "w") as f:
            f.write(f"# Custom agent: {name}\n")
            f.write(f"# Added via dashboard\n\n")
            f.write(code)
        return {"ok": True, "path": path, "msg": f"saved — restart bot to activate"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/agents/custom/code/{name}")
def delete_custom_agent_code(name: str):
    """Delete a custom agent file"""
    path = f"agents/trading/custom_{name}.py"
    try:
        if os.path.exists(path):
            os.remove(path)
            return {"ok": True, "msg": f"deleted {path}"}
        return {"ok": False, "msg": "file not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents/custom/code")
def list_custom_agent_code():
    """List all custom agent files"""
    import glob
    files = glob.glob("agents/trading/custom_*.py")
    agents = []
    for f in files:
        name = os.path.basename(f).replace("custom_", "").replace(".py", "")
        with open(f) as fp:
            content = fp.read()
        agents.append({"name": name, "path": f, "code": content})
    return {"agents": agents}

@app.delete("/agents/custom/{name}")
def delete_custom_agent(name: str):
    try:
        import sqlite3
        db = sqlite3.connect("core/brain.db")
        db.execute("DELETE FROM custom_agents WHERE name=?", (name,))
        db.commit()
        db.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/robot/deactivate")
def robot_deactivate(req: RobotRequest):
    try:
        from trading import deactivate_robot
        deactivate_robot(req.user_id, req.robot_id)
        return {"ok": True, "robot": req.robot_id, "action": "deactivated"}
    except ImportError:
        return {"ok": False, "error": "trading.py not available"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOT CONTROL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/bot/start")
def start_bot():
    global _bot_process
    if bot_running():
        return {"ok": False, "msg": "already running"}
    loop_path = BOT_DIR / "loop.py"
    if not loop_path.exists():
        return {"ok": False, "msg": "loop.py not found"}
    _bot_process = subprocess.Popen(
        [sys.executable, str(loop_path)],
        cwd=str(BOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"ok": True, "pid": _bot_process.pid}

@app.post("/bot/stop")
def stop_bot():
    global _bot_process
    if _bot_process and _bot_process.poll() is None:
        _bot_process.terminate()
        _bot_process = None
        return {"ok": True, "msg": "bot stopped"}
    return {"ok": False, "msg": "bot not running via API"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PORTFOLIO / TRADES  (extra endpoints used by bot internally)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/portfolio")
def get_portfolio_data():
    try:
        cash = get_portfolio() if PAPER_OK else 1000.0
    except:
        cash = 1000.0
    positions, realized_pnl, wins, losses = [], 0.0, 0, 0
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT token, entry_price, size_usd, pnl_pct FROM positions WHERE status='OPEN'"
            ).fetchall()
            for r in rows:
                positions.append({
                    "token": r[0], "entry_price": r[1],
                    "size_usd": r[2], "pnl_pct": r[3],
                })
            closed = conn.execute(
                "SELECT SUM(pnl_usd), COUNT(*) FROM positions WHERE status='CLOSED'"
            ).fetchone()
            realized_pnl = round(closed[0] or 0, 2)
            wins   = conn.execute("SELECT COUNT(*) FROM positions WHERE status='CLOSED' AND pnl_usd > 0").fetchone()[0]
            losses = conn.execute("SELECT COUNT(*) FROM positions WHERE status='CLOSED' AND pnl_usd <= 0").fetchone()[0]
    except:
        pass
    total = wins + losses
    return {
        "cash": round(cash, 2),
        "realized_pnl": realized_pnl,
        "win_rate": round(wins / max(total, 1) * 100, 1),
        "wins": wins, "losses": losses,
        "positions": positions,
    }

@app.get("/trades")
def get_trades(limit: int = 20):
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT token, action, price, size_usd, pnl_usd, reason, timestamp "
                "FROM trade_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {"token": r[0], "action": r[1], "price": r[2],
             "size": r[3], "pnl": r[4], "reason": r[5], "ts": r[6]}
            for r in rows
        ]
    except:
        return []

@app.get("/scans")
def get_scan_log(limit: int = 10):
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT tokens_scanned, tokens_approved, top_token, timestamp "
                "FROM scan_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"scanned": r[0], "approved": r[1], "top": r[2], "ts": r[3]} for r in rows]
    except:
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ── Helius Webhook ─────────────────────────────────────────────────────────────
@app.post("/webhook/helius")
async def helius_webhook(payload: dict):
    try:
        for txn in payload if isinstance(payload, list) else [payload]:
            txn_type = txn.get("type", "UNKNOWN")
            source   = txn.get("source", "?")
            sig      = txn.get("signature", "")[:12]
            accs     = txn.get("accountData", [])
            wallet   = accs[0].get("account", "?") if accs else "?"
            msg = f"{wallet[:6]}.. | {txn_type} via {source} | {sig}.."
            brain_db = sqlite3.connect("/home/kazgar/BR0THER-H00D/core/brain.db")
            brain_db.execute("INSERT OR IGNORE INTO memory (agent, key, value) VALUES (?,?,?)",
                           ("helius_webhook", sig, msg))
            brain_db.commit()
            brain_db.close()
            print(f"  [Helius webhook] {msg}")
        return {"ok": True}
    except Exception as e:
        print(f"  [Helius webhook] error: {e}")
        return {"ok": False, "error": str(e)}

# ── $H00D Token Gate ───────────────────────────────────────────────────────────
from hood_gate import router as gate_router
app.include_router(gate_router)

# ── Serve terminal website ─────────────────────────────────────────────────────
@app.get("/terminal")
def terminal_ui():
    return FileResponse("hood_web.html")

# ── Chat endpoint ──────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    wallet: str = ""

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        from ai_engine import ask
        reply = await ask(req.message)
        return {"reply": reply}
    except Exception as e:
        return {"reply": f"agent unavailable: {e}"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  XTERM WEBSOCKET TERMINAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import asyncio
import pty
import fcntl
import termios
import struct
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    await websocket.accept()
    master_fd, slave_fd = pty.openpty()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(BOT_DIR / "Start.py"),
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        cwd=str(BOT_DIR),
        env={**os.environ, "TERM": "xterm-256color", "COLUMNS": "120", "LINES": "40"},
    )
    os.close(slave_fd)

    async def read_output():
        loop = asyncio.get_event_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, os.read, master_fd, 1024)
                if not data:
                    break
                await websocket.send_bytes(data)
        except Exception:
            pass

    asyncio.create_task(read_output())

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg:
                os.write(master_fd, msg["bytes"])
            elif "text" in msg:
                data = msg["text"]
                if data.startswith("resize:"):
                    _, cols, rows = data.split(":")
                    winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                else:
                    os.write(master_fd, data.encode())
    except WebSocketDisconnect:
        pass
    finally:
        try:
            proc.kill()
            os.close(master_fd)
        except:
            pass

@app.get("/xterm")
def xterm_ui():
    return FileResponse("terminal.html")
