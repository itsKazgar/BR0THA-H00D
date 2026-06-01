"""
CONSENSUS ENGINE — The Brotherhood Vote
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Every trade goes through a council vote before execution.
Each agent has a role, a weight, and a vote.
Risk manager has veto power.
Memory keeper weighs in from past trades.
3/5 votes needed to buy.
"""
import json, time, os
from datetime import datetime
from core import brain

CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'; BD='\033[1m'; DM='\033[2m'; RS='\033[0m'

# ── Council members & their weights ──────────────
COUNCIL = [
    {"name": "Analyst",       "weight": 3, "role": "AI reasoning"},
    {"name": "Risk Manager",  "weight": 3, "role": "safety guard", "veto": True},
    {"name": "Whale Tracker", "weight": 2, "role": "smart money"},
    {"name": "Pump Hunter",   "weight": 2, "role": "early gems"},
    {"name": "Memory Keeper", "weight": 2, "role": "past lessons"},
    {"name": "News Scout",    "weight": 1, "role": "sentiment"},
    {"name": "Scanner",       "weight": 1, "role": "signal source"},
]

VOTES_NEEDED = 9  # weighted votes needed to pass

def _vote_analyst(coin: dict, score: int, reasons: list) -> dict:
    """Analyst votes based on score + LLM reasoning."""
    from core.analyst import should_buy
    result = should_buy(coin, score, reasons)
    vote = result.get("buy", False)
    conf = result.get("confidence", 50)
    return {
        "vote":   vote,
        "conf":   conf,
        "reason": result.get("thesis", "")[:80],
        "mode":   result.get("mode", "rules"),
    }

def _vote_risk_manager(coin: dict, score: int) -> dict:
    """Risk manager vetoes if any red flags."""
    name  = coin.get("name", "?")
    mcap  = coin.get("mcap", 0)
    age   = coin.get("age_hrs", 0)
    liq   = coin.get("liquidity", 0)
    ch1h  = coin.get("change_1h", 0)
    vol   = coin.get("volume_24h", 0)

    flags = []
    if age > 48:          flags.append(f"too old ({age:.0f}h)")
    if liq < 20_000:      flags.append(f"thin liq (${liq:,.0f})")
    if ch1h > 40:         flags.append(f"already pumped {ch1h:.0f}%")
    if mcap > 50_000_000: flags.append(f"mcap too large (${mcap:,.0f})")
    if vol < 20_000:      flags.append(f"low vol (${vol:,.0f})")

    # Block trades in bearish market conditions
    sent_mems = brain.recall(type="sentiment", limit=5)
    bearish_count = 0
    for m in sent_mems:
        c = m["content"].lower()
        if "bearish" in c or "fear" in c or "dumping" in c:
            bearish_count += 1
    if bearish_count >= 3:
        flags.append(f"bearish market ({bearish_count}/5 signals bearish)")

    # Check recent risk alerts from brain
    risk_mems = brain.recall(agent="risk_manager", limit=5)
    for m in risk_mems:
        if name.lower() in m["content"].lower() and "ALERT" in m["content"]:
            flags.append("prior risk alert")
            break

    vote = len(flags) == 0
    reason = f"flags: {', '.join(flags)}" if flags else "all checks passed"
    return {"vote": vote, "conf": 90 if vote else 10, "reason": reason}

def _vote_whale_tracker(coin: dict) -> dict:
    """Votes YES if whales recently bought this coin."""
    name = coin.get("name", "").lower()
    mint = coin.get("mint", "")
    mems = brain.recall(type="whale_alert", limit=30)
    for m in mems:
        c = m["content"].lower()
        if name in c or (mint and mint[:8].lower() in c):
            return {"vote": True, "conf": 80,
                    "reason": f"whale activity detected"}
    return {"vote": False, "conf": 40,
            "reason": "no whale activity found"}

def _vote_pump_hunter(coin: dict, score: int) -> dict:
    """Votes YES if pump hunter flagged this as a gem."""
    name = coin.get("name", "").lower()
    mint = coin.get("mint", "")
    mems = brain.recall(type="pump_gem", limit=30)
    for m in mems:
        c = m["content"].lower()
        if name in c or (mint and mint[:8].lower() in c):
            return {"vote": True, "conf": 75,
                    "reason": "pump hunter flagged as gem"}
    # Fall back to score
    vote = score >= 55
    return {"vote": vote, "conf": score,
            "reason": f"score={score}/100"}

def _vote_memory_keeper(coin: dict) -> dict:
    """Votes based on past trade outcomes for similar coins."""
    name = coin.get("name", "").lower()
    past = brain.get_learnings(topic=name, limit=5)

    wins = losses = 0
    notes = []
    for l in past:
        insight = l["insight"].lower()
        if "win" in insight or "profit" in insight or "+%" in insight:
            wins += 1
        elif "loss" in insight or "stop" in insight or "-%" in insight:
            losses += 1
        notes.append(l["insight"][:50])

    if wins > losses:
        return {"vote": True,  "conf": 70,
                "reason": f"past record: {wins}W/{losses}L"}
    elif losses > wins:
        return {"vote": False, "conf": 65,
                "reason": f"past losses: {wins}W/{losses}L"}
    else:
        return {"vote": True,  "conf": 50,
                "reason": "no past data — neutral"}

def _vote_news_scout(coin: dict) -> dict:
    """Votes based on recent sentiment."""
    mems = brain.recall(type="sentiment", limit=10)
    bullish = bearish = 0
    for m in mems:
        c = m["content"].lower()
        if any(w in c for w in ["bullish","pump","moon","buy","surge"]):
            bullish += 1
        elif any(w in c for w in ["bearish","dump","sell","crash","rug"]):
            bearish += 1
    if bearish > bullish:
        return {"vote": False, "conf": 60,
                "reason": f"bearish sentiment ({bearish} signals)"}
    return {"vote": True, "conf": 55,
            "reason": f"neutral/bullish sentiment"}

def _vote_scanner(coin: dict, score: int) -> dict:
    """Scanner always votes — it found the signal."""
    return {"vote": score >= 62, "conf": score,
            "reason": f"scanner score {score}/100"}

# ── Main vote function ────────────────────────────
def council_vote(coin: dict, score: int, reasons: list) -> dict:
    """
    Run the full brotherhood vote.
    Returns {
        "approved": bool,
        "votes_for": int,
        "votes_against": int,
        "vetoed": bool,
        "results": [...],
        "summary": str
    }
    """
    name = coin.get("name", "?")
    now  = datetime.now().strftime("%H:%M:%S")

    print(f"\n{CY}{BD}╔══════════════════════════════════════════════╗{RS}")
    print(f"{CY}{BD}║  🗳️  BROTHERHOOD VOTE — {name:<20} ║{RS}")
    print(f"{CY}{BD}╠══════════════════════════════════════════════╣{RS}")

    # Collect all votes
    raw_votes = {
        "Analyst":       _vote_analyst(coin, score, reasons),
        "Risk Manager":  _vote_risk_manager(coin, score),
        "Whale Tracker": _vote_whale_tracker(coin),
        "Pump Hunter":   _vote_pump_hunter(coin, score),
        "Memory Keeper": _vote_memory_keeper(coin),
        "News Scout":    _vote_news_scout(coin),
        "Scanner":       _vote_scanner(coin, score),
    }

    results   = []
    total_for = 0
    total_ag  = 0
    vetoed    = False

    for member in COUNCIL:
        mname  = member["name"]
        weight = member["weight"]
        is_veto= member.get("veto", False)
        v      = raw_votes[mname]

        vote   = v["vote"]
        conf   = v["conf"]
        reason = v["reason"]

        weighted = weight if vote else 0
        if vote:
            total_for += weight
        else:
            total_ag  += weight

        # Veto check
        if is_veto and not vote:
            vetoed = True

        emoji = f"{GR}✅{RS}" if vote else f"{RD}❌{RS}"
        veto_tag = f" {RD}[VETO]{RS}" if (is_veto and not vote) else ""
        print(f"  {emoji} {BD}{mname:<14}{RS} {DM}w={weight}{RS}  {reason[:45]}{veto_tag}")

        results.append({
            "agent":   mname,
            "vote":    vote,
            "weight":  weight,
            "conf":    conf,
            "reason":  reason,
            "veto":    is_veto and not vote,
        })

    # Final decision
    approved = (total_for >= VOTES_NEEDED) and not vetoed

    status_color = GR if approved else RD
    status_text  = "APPROVED" if approved else ("VETOED" if vetoed else "REJECTED")

    print(f"{CY}{BD}╠══════════════════════════════════════════════╣{RS}")
    print(f"  {BD}Votes FOR :{RS} {GR}{total_for}{RS}  |  "
          f"{BD}Against:{RS} {RD}{total_ag}{RS}  |  "
          f"{BD}Needed:{RS} {VOTES_NEEDED}")
    print(f"  {status_color}{BD}VERDICT: {status_text}{RS}")
    print(f"{CY}{BD}╚══════════════════════════════════════════════╝{RS}")

    summary = (f"VOTE {status_text} {name} | "
               f"for={total_for} against={total_ag} | "
               f"vetoed={vetoed}")

    # Log to brain
    brain.remember("consensus",
        summary,
        type="council_vote",
        tags=f"{name.lower()},vote,{'approved' if approved else 'rejected'}")

    return {
        "approved":      approved,
        "votes_for":     total_for,
        "votes_against": total_ag,
        "vetoed":        vetoed,
        "results":       results,
        "summary":       summary,
        "status":        status_text,
    }
