"""
MEMORY KEEPER AGENT
────────────────────
Runs every 5 minutes. Reads everything the team has done this session:
- trades, signals, whale alerts, news sentiment, risk warnings
- Summarizes key learnings
- Keeps a running performance log
- Posts a "team briefing" to brain every cycle
Uses LLM if available, falls back to structured summary.
"""
import sys, os, time, json, requests
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

INTERVAL  = 300  # 5 minutes
GROQ_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_URL  = "https://api.groq.com/openai/v1/chat/completions"

def think(prompt: str) -> str:
    if not GROQ_KEY:
        return ""
    try:
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model":       "llama3-8b-8192",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  500,
                "temperature": 0.4,
            }, timeout=15)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return ""

def summarize():
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] 🧠 MEMORY KEEPER compiling session summary...")

    # Gather everything from this session
    trades      = brain.recall(type="trade",         limit=50)
    signals     = brain.recall(type="trade_signal",  limit=30)
    verdicts    = brain.recall(agent="analyst",      limit=20)
    whale_alerts= brain.recall(type="whale_alert",   limit=20)
    risk_alerts = brain.recall(type="risk_alert",    limit=20)
    sentiment   = brain.recall(type="sentiment",     limit=10)
    learnings   = brain.get_learnings(limit=20)

    # ── Performance stats ──────────────────────────────
    buys  = [t for t in trades if "BUY"  in t["content"]]
    sells = [t for t in trades if "SELL" in t["content"]]

    wins = losses = 0
    pnl_total = 0.0
    for s in sells:
        try:
            pnl_str = s["content"].split("PnL=$")[1].split(" ")[0]
            pnl = float(pnl_str.replace("+",""))
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
            pnl_total += pnl
        except:
            pass

    total_trades = len(buys)
    win_rate     = wins / max(wins + losses, 1) * 100

    print(f"  📊 Session stats:")
    print(f"     Signals found : {len(signals)}")
    print(f"     Trades taken  : {total_trades}")
    print(f"     Wins / Losses : {wins} / {losses}  ({win_rate:.0f}% win rate)")
    print(f"     Session PnL   : ${pnl_total:+.2f}")
    print(f"     Whale alerts  : {len(whale_alerts)}")
    print(f"     Risk alerts   : {len(risk_alerts)}")

    # ── Past learnings ─────────────────────────────────
    if learnings:
        print(f"\n  📚 Team knowledge base ({len(learnings)} entries):")
        for l in learnings[:5]:
            print(f"     [{l['topic']}] {l['insight'][:80]}")

    # ── LLM team briefing ──────────────────────────────
    if GROQ_KEY:
        trade_log  = "\n".join(t["content"][:120] for t in trades[:10])
        signal_log = "\n".join(s["content"][:80]  for s in signals[:5])
        risk_log   = "\n".join(r["content"][:80]  for r in risk_alerts[:5])
        sent_log   = "\n".join(s["content"][:100] for s in sentiment[:3])

        prompt = f"""You are the memory keeper for a crypto trading team called BR0THER-H00D.
Summarize this session's activity and give 3 key learnings for the team.

TRADES:
{trade_log or 'none'}

SIGNALS:
{signal_log or 'none'}

RISK ALERTS:
{risk_log or 'none'}

MARKET SENTIMENT:
{sent_log or 'none'}

Give:
1. A 2-sentence session summary
2. Top 3 lessons learned (numbered)
3. One recommendation for next session

Keep it sharp and practical."""

        briefing = think(prompt)
        if briefing:
            print(f"\n  🧠 AI BRIEFING:\n")
            for line in briefing.split("\n"):
                print(f"     {line}")

            brain.remember("memory_keeper",
                f"SESSION BRIEFING: {briefing[:500]}",
                type="briefing", tags="summary,session")

            # Extract and save learnings
            for line in briefing.split("\n"):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("-")):
                    brain.learn("memory_keeper", "session_lesson", line[:200])
    else:
        # Rule-based summary
        summary = (f"Session: {total_trades} trades | {wins}W/{losses}L | "
                   f"PnL=${pnl_total:+.2f} | {len(signals)} signals | "
                   f"{len(whale_alerts)} whale alerts")
        brain.remember("memory_keeper", summary, type="briefing", tags="summary")
        print(f"\n  📝 {summary}")

    # Save performance to state
    perf = brain.load_state("memory_keeper")
    sessions = perf.get("sessions", [])
    sessions.append({
        "ts":          datetime.now().isoformat(),
        "trades":      total_trades,
        "wins":        wins,
        "losses":      losses,
        "pnl":         pnl_total,
        "signals":     len(signals),
        "whale_alerts":len(whale_alerts),
    })
    brain.save_state("memory_keeper", {"sessions": sessions[-50:]})  # keep last 50

def run():
    brain.init_db()
    print("🧠 MEMORY KEEPER started — logging team activity every 5 min\n")
    # First summary after 2 min (let others collect data first)
    time.sleep(120)
    while True:
        try:
            summarize()
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\n[memory_keeper] stopped.")
            break
        except Exception as e:
            print(f"[memory_keeper] error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
