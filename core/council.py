"""
THE COUNCIL — Freemason hierarchy for BR0THER-H00D
The Tome, Ranks, Seals, Circles, and Council Feed.
"""
import os, sys, json, requests
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain

# ═══════════════════════════════════════════
# RANKS — earned through interactions
# ═══════════════════════════════════════════
RANKS = [
    (0,   "Initiate",    "○"),
    (10,  "Apprentice",  "◎"),
    (25,  "Fellow",      "●"),
    (50,  "Master",      "◈"),
    (100, "Grand Master","🔺"),
]

# ═══════════════════════════════════════════
# CIRCLES — which brother belongs where
# ═══════════════════════════════════════════
CIRCLES = {
    "intel": {
        "name":    "Intel Circle",
        "emoji":   "📡",
        "degree":  "First",
        "brothers": ["alpha", "search", "hn", "reddit", "scraper"],
        "mandate": "Gather intelligence. Never act on it directly.",
    },
    "money": {
        "name":    "Money Circle",
        "emoji":   "💰",
        "degree":  "Second",
        "brothers": ["crypto", "stocks", "portfolio", "alerts"],
        "mandate": "Track the bag. Never guess. Only report.",
    },
    "ops": {
        "name":    "Ops Circle",
        "emoji":   "🛠️",
        "degree":  "Third",
        "brothers": ["tasks", "telegram", "weather"],
        "mandate": "Execute. No questions. No hesitation.",
    },
    "counsel": {
        "name":    "The Counsel",
        "emoji":   "🌅",
        "degree":  "Sacred",
        "brothers": ["briefing"],
        "mandate": "Speak truth to the master every dawn.",
    },
    "command": {
        "name":    "Grand Command",
        "emoji":   "🔺",
        "degree":  "Supreme",
        "brothers": ["orchestrator"],
        "mandate": "See all. Decide all. Nothing moves without blessing.",
    },
}

def get_circle(brother_id: str) -> dict:
    """Get which circle a brother belongs to."""
    for cid, circle in CIRCLES.items():
        if brother_id in circle["brothers"]:
            return {**circle, "circle_id": cid}
    return {"name": "Unknown", "emoji": "?", "degree": "None", "circle_id": "unknown"}

def get_rank(brother_id: str) -> tuple:
    """Get current rank based on interaction count."""
    state = brain.load_state(f"personality_{brother_id}") or {}
    count = state.get("interaction_count", 0)
    rank  = RANKS[0]
    for threshold, title, symbol in RANKS:
        if count >= threshold:
            rank = (threshold, title, symbol)
    return rank

def get_seal(brother_id: str) -> str:
    """Get a brother's full seal — circle + rank."""
    circle = get_circle(brother_id)
    _, rank_title, rank_symbol = get_rank(brother_id)
    return f"{circle['emoji']} [{rank_symbol} {rank_title}] {circle['degree']} Degree"

# ═══════════════════════════════════════════
# THE TOME — shared signal ledger
# ═══════════════════════════════════════════
def inscribe(brother_id: str, signal: str, signal_type: str = "intel"):
    """Write to the shared Tome — all brothers can read this."""
    brain.remember(
        agent   = brother_id,
        content = signal,
        type    = f"tome_{signal_type}",
        tags    = f"tome,{signal_type},{brother_id}"
    )

def read_tome(signal_type: str = None, limit: int = 20) -> list:
    """Read recent entries from the Tome."""
    if signal_type:
        return brain.recall(type=f"tome_{signal_type}", limit=limit)
    # Read all tome entries
    with brain._conn() as c:
        rows = c.execute(
            "SELECT * FROM memories WHERE tags LIKE '%tome%' ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

def read_circle_tome(circle_id: str, limit: int = 5) -> list:
    """Read what a specific circle has reported recently."""
    brothers = CIRCLES.get(circle_id, {}).get("brothers", [])
    results  = []
    for b in brothers:
        entries = brain.recall(agent=b, limit=3)
        for e in entries:
            if "tome" in e.get("tags", ""):
                results.append(e)
    return sorted(results, key=lambda x: x["id"], reverse=True)[:limit]

# ═══════════════════════════════════════════
# COUNCIL FEED — live board of today's signals
# ═══════════════════════════════════════════
def post_to_feed(brother_id: str, signal: str):
    """Post a signal to the council feed."""
    inscribe(brother_id, signal, signal_type="feed")

def get_feed(limit: int = 15) -> list:
    """Get the live council feed."""
    return read_tome(signal_type="feed", limit=limit)

# ═══════════════════════════════════════════
# COUNCIL MEETING — full report from all circles
# ═══════════════════════════════════════════
def convene(task: str = "morning briefing") -> str:
    """
    Convene the full council — gather reports from all circles
    and synthesize into one verdict.
    """
    key = os.getenv("GROQ_API_KEY", "")
    
    lines = []
    lines.append("╔══════════════════════════════════════════════╗")
    lines.append("║      🔺 THE COUNCIL IS CONVENED 🔺           ║")
    lines.append(f"║  {datetime.now().strftime('%A %B %d %Y  %H:%M'):^42}  ║")
    lines.append("╚══════════════════════════════════════════════╝")
    lines.append("")

    circle_reports = {}

    for cid, circle in CIRCLES.items():
        if cid == "command":
            continue
        
        # Get recent tome entries from this circle's brothers
        entries = []
        seen = set()
        for bid in circle["brothers"]:
            recent = brain.recall(agent=bid, limit=3)
            for e in recent:
                c = e.get("content", "")
                if not c or len(c) <= 10:
                    continue
                # skip near-duplicates (first 50 chars match)
                fingerprint = c[:50].lower()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                entries.append(f"{bid}: {c[:120]}")

        if entries:
            circle_reports[cid] = entries
            lines.append(f"{circle['emoji']} {circle['name'].upper()} — {circle['degree']} Degree")
            lines.append(f"   Mandate: {circle['mandate']}")
            for e in entries[:3]:
                lines.append(f"   • {e[:100]}")
            lines.append("")

    # Grand Master synthesis
    if key and circle_reports:
        context = "\n".join(
            f"[{cid}]: " + " | ".join(r[:80] for r in reports[:2])
            for cid, reports in circle_reports.items()
        )
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": 400,
                      "temperature": 0.3,
                      "messages": [{"role": "user", "content":
                          f"You are the editor of a daily brief read by curious, "
                          f"plugged-in people. You speak for the whole desk in one voice: "
                          f"sharp, calm, a little dry, zero hype. Task: {task}.\n\n"
                          f"What the desk gathered:\n{context}\n\n"
                          f"Write the brief:\n"
                          f"- Open with one line that frames the day. Then the lead item: "
                          f"the single most important thing, and why it matters in plain terms.\n"
                          f"- Then 3-5 'also worth knowing' items across the different topics, "
                          f"one tight line each. Favor variety across topics over depth on one.\n"
                          f"- Close with one 'worth watching' line.\n"
                          f"- Use only what's in the reports. Mark anything uncertain as "
                          f"'likely' or 'reportedly'. Never invent figures, dates, or quotes.\n"
                          f"- Report what's happening and what to watch. Do NOT give financial, "
                          f"medical, or trading advice, predict prices, or use roleplay language.\n"
                          f"- Clean, readable, consistent voice every day. No preamble before the brief."}]},
                timeout=15)
            if r.status_code == 200:
                verdict = r.json()["choices"][0]["message"]["content"].strip()
                lines.append("━" * 48)
                lines.append("🔺 GRAND MASTER'S VERDICT")
                lines.append("")
                lines.append(verdict)
                lines.append("")
        except:
            pass

    lines.append("━" * 48)
    lines.append("🔺 Council adjourned. The Eye remains open.")
    return "\n".join(lines)

# ═══════════════════════════════════════════
# BROTHERHOOD STATUS
# ═══════════════════════════════════════════
def brotherhood_status() -> str:
    """Full status of the brotherhood — all brothers, ranks, circles."""
    lines = []
    lines.append("╔══════════════════════════════════════════════╗")
    lines.append("║         THE BR0THER-H00D COUNCIL             ║")
    lines.append("║              All Seeing. All Knowing.         ║")
    lines.append("╚══════════════════════════════════════════════╝")
    lines.append("")

    for cid, circle in CIRCLES.items():
        lines.append(f"{circle['emoji']} {circle['name'].upper()} — {circle['degree']} Degree")
        for bid in circle["brothers"]:
            _, rank_title, rank_symbol = get_rank(bid)
            state = brain.load_state(f"personality_{bid}") or {}
            count = state.get("interaction_count", 0)
            traits = state.get("traits", "seed personality")[:50]
            lines.append(f"   {rank_symbol} {bid:15} [{rank_title:12}] {count:3} ops | {traits}")
        lines.append("")

    # Tome stats
    tome = read_tome(limit=100)
    lines.append(f"📜 THE TOME: {len(tome)} entries inscribed")
    feed = get_feed(limit=5)
    if feed:
        lines.append(f"\n📡 LATEST COUNCIL FEED:")
        for f in feed[:5]:
            lines.append(f"   • [{f['agent']}] {f['content'][:80]}")

    return "\n".join(lines)
