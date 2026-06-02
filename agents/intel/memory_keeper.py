CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'; BD='\033[1m'; DM='\033[2m'; RS='\033[0m'
import time, sys, os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain
from core.llm import think

INTERVAL = 300  # every 5 mins

def cleanup():
    """Keep brain lean — trim old low-value memories."""
    import sqlite3
    db   = "/home/kazgar/BR0THER-H00D/core/brain.db"
    conn = sqlite3.connect(db)

    # How many of each type to keep
    KEEP = {
        "idea":          20,   # scanner ideas — rotate fast
        "trade_signal":  30,   # recent signals
        "council_vote":  20,   # recent votes
        "pump_gem":      30,   # pump hunter finds
        "whale_alert":   30,   # whale activity
        "sentiment":     20,   # news sentiment
        "risk_alert":    20,   # risk warnings
        "trade":         999,  # keep ALL trade history forever
        "learning":      999,  # keep ALL learnings forever
        "session_summary": 50, # keep recent summaries
    }

    total_deleted = 0
    for memory_type, keep in KEEP.items():
        # Delete everything older than the most recent N of this type
        deleted = conn.execute(f"""
            DELETE FROM memories
            WHERE type = ?
            AND id NOT IN (
                SELECT id FROM memories
                WHERE type = ?
                ORDER BY id DESC
                LIMIT ?
            )
        """, (memory_type, memory_type, keep)).rowcount
        if deleted > 0:
            total_deleted += deleted

    conn.commit()

    # Vacuum to reclaim disk space
    if total_deleted > 0:
        conn.execute("VACUUM")
        print(f"  🧹 Brain cleanup: removed {total_deleted} old memories")

    size = os.path.getsize(db) / 1024
    total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    conn.close()
    print(f"  📦 Brain: {total} memories  {size:.1f} KB")

def summarize():
    now     = datetime.now().strftime("%H:%M:%S")
    state   = brain.load_state("trader")
    history = state.get("history", [])
    balance = state.get("balance", 100)
    pnl     = state.get("total_pnl", 0)

    if not history:
        print(f"  [{now}] 🧠 no trades yet to learn from")
        return

    wins   = [t for t in history if t["pnl_pct"] > 0]
    losses = [t for t in history if t["pnl_pct"] <= 0]
    total  = len(history)
    wr     = len(wins)/total*100 if total else 0

    # Source performance
    src_wins  = {}
    src_total = {}
    for t in history:
        for s in t.get("sources", []):
            src_total[s] = src_total.get(s, 0) + 1
            if t["pnl_pct"] > 0:
                src_wins[s] = src_wins.get(s, 0) + 1

    best_source = max(src_total, key=lambda s: src_wins.get(s,0)/src_total[s], default="none") if src_total else "none"

    # Best and worst coins
    if history:
        best  = max(history, key=lambda t: t["pnl_pct"])
        worst = min(history, key=lambda t: t["pnl_pct"])
    else:
        best = worst = None

    # Recent signals from brain
    signals  = brain.recall(type="trade_signal", limit=10)
    rejected = brain.recall(type="rejected", limit=5)

    summary = (f"SESSION SUMMARY | trades={total} WR={wr:.0f}% | "
               f"wins={len(wins)} losses={len(losses)} | "
               f"pnl=${pnl:+.2f} bal=${balance:.2f} | "
               f"best_source={best_source}")

    if best:
        summary += f" | best={best['name']}+{best['pnl_pct']:.1f}% worst={worst['name']}{worst['pnl_pct']:.1f}%"

    print(f"\n{CY}{BD}╔══════════════════════════════════════╗{RS}")
    print(f"{CY}{BD}║  🧠 MEMORY KEEPER  {now}           ║{RS}")
    print(f"  Trades: {total}  WR: {wr:.0f}%  PnL: ${pnl:+.2f}")
    if best_source != "none":
        bwr = src_wins.get(best_source,0)/src_total[best_source]*100
        print(f"  Best source: {best_source} ({bwr:.0f}% WR)")
    if best:
        print(f"  Best trade : {GR}{best['name']} +{best['pnl_pct']:.1f}%{RS}")
        print(f"  Worst trade: {RD}{worst['name']} {worst['pnl_pct']:.1f}%{RS}")

    # Save summary to brain
    brain.remember("memory_keeper", summary,
        type="session_summary",
        tags="summary,learning")

    # Try LLM insight if available
    if total >= 3:
        trade_lines = "\n".join([
            f"{t['name']} {t['pnl_pct']:+.1f}% held={t['held_mins']}min reason={t['reason']}"
            for t in history[-10:]
        ])
        prompt = (f"You are analyzing a Solana memecoin trading bot's performance.\n"
                  f"Recent trades:\n{trade_lines}\n\n"
                  f"Win rate: {wr:.0f}%  PnL: ${pnl:+.2f}\n\n"
                  f"Give ONE specific insight to improve performance. Be concise (1-2 sentences).")

        resp, source = think(prompt)
        if resp:
            insight = resp.strip()[:200]
            print(f"  {CY}🤖 AI insight ({source}):{RS} {insight}")
            brain.learn("memory_keeper", "strategy", insight)

    cleanup()
    print(f"{CY}{BD}╚══════════════════════════════════════╝{RS}\n")

def run():
    brain.init_db()
    import os
    print(f"{CY}{BD}🧠 MEMORY KEEPER{RS} — logging learnings every {INTERVAL//60} mins")
    print(f"   Press Ctrl+C to stop\n")
    time.sleep(30)  # wait for other agents to start
    summarize()
    while True:
        try:
            time.sleep(INTERVAL)
            summarize()
        except KeyboardInterrupt:
            print("\n[memory_keeper] stopped.")
            break
        except Exception as e:
            print(f"[memory_keeper] error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
