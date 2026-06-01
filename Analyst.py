"""
ANALYST AGENT
─────────────
Reads scanner signals + risk manager warnings.
Uses Groq LLM to reason about each trade. Posts verdicts back to brain.
Runs every 30s alongside scanner.
"""
import sys, os, time, requests, json
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core import brain

from core.llm import think as llm_think, status as llm_status
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
INTERVAL = 30

def think(prompt: str) -> str:
    if not GROQ_KEY:
        return "[no_llm]"
    try:
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.3,
            }, timeout=15)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[groq error: {e}]"

def analyze_signals():
    signals  = brain.recall(type="trade_signal", limit=10)
    risk_mem = brain.recall(agent="risk_manager", limit=5)
    risk_ctx = " | ".join(m["content"][:80] for m in risk_mem) or "no risk warnings"

    if not signals:
        return

    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] 📊 ANALYST reviewing {len(signals)} signal(s)...")

    for s in signals:
        c = s["content"]
        if "BUY" not in c:
            continue
        # Skip if already analyzed
        already = brain.recall(agent="analyst", limit=50)
        signal_key = c[:40]
        if any(signal_key in a["content"] for a in already):
            continue

        # Parse signal
        try:
            parts  = c.split("|")
            name   = parts[0].split("BUY")[1].split("@")[0].strip()
            price  = parts[0].split("@")[1].strip().replace("$","")
            score  = [p for p in parts if "score=" in p][0].split("=")[1].strip()
            rest   = " | ".join(parts[1:])
        except:
            continue

        if not GROQ_KEY:
            # Rule-based fallback
            sc = int(score) if score.isdigit() else 0
            verdict = "BUY" if sc >= 70 else "SKIP"
            brain.remember("analyst",
                f"VERDICT {verdict} {name} score={score} | rule-based (no LLM)",
                type="analyst_verdict", tags=f"{name.lower()},verdict")
            print(f"  [analyst] {name}: {verdict} (rule-based, score={score})")
            continue

        # LLM analysis
        learnings = brain.get_learnings(topic=name, limit=3)
        past = " | ".join(l["insight"] for l in learnings) or "no past trades on this coin"

        prompt = f"""You are a sharp Solana memecoin trader on a team. Analyze this signal.

SIGNAL: {c[:300]}
RISK CONTEXT: {risk_ctx}
PAST TRADES ON {name}: {past}

Give a short verdict:
1. BUY or SKIP
2. Confidence 0-100
3. One-line thesis
4. Biggest risk

Respond ONLY as JSON: {{"verdict":"BUY","confidence":75,"thesis":"...","risk":"..."}}"""

        raw = think(prompt)
        try:
            clean  = raw[raw.find("{"):raw.rfind("}")+1]
            result = json.loads(clean)
            verdict    = result.get("verdict", "SKIP")
            confidence = result.get("confidence", 50)
            thesis     = result.get("thesis", "")
            risk       = result.get("risk", "")
        except:
            verdict, confidence, thesis, risk = "SKIP", 50, "parse error", "unknown"

        brain.remember("analyst",
            f"VERDICT {verdict} {name} | conf={confidence} | {thesis} | risk={risk} | signal={signal_key}",
            type="analyst_verdict", tags=f"{name.lower()},verdict")

        emoji = "✅" if verdict == "BUY" else "❌"
        print(f"  {emoji} {name}: {verdict} conf={confidence} | {thesis}")
        if risk:
            print(f"     ⚠️  Risk: {risk}")

def run():
    brain.init_db()
    print("🧠 ANALYST agent started — reasoning on every signal")
    print(f"   LLM: {'Groq llama3' if GROQ_KEY else 'rule-based (add GROQ_API_KEY)'}\n")
    while True:
        try:
            analyze_signals()
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\n[analyst] stopped.")
            break
        except Exception as e:
            print(f"[analyst] error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
