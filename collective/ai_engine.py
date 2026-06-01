import os, requests, time
from dotenv import load_dotenv
load_dotenv(override=True)

CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY", "")
GROQ_KEY     = os.getenv("GROQ_API_KEY", "")

# ── PROVIDERS ──────────────────────────────────────────────────────────────────

def ask_groq(prompt, system, model="llama-3.3-70b-versatile"):
    if not GROQ_KEY:
        raise Exception("No Groq key")
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={"model": model, "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ], "max_tokens": 600},
        timeout=30
    )
    if r.status_code == 429:
        time.sleep(3)
        raise Exception("Groq rate limit")
    if r.status_code != 200:
        raise Exception("Groq error: " + r.text[:100])
    return r.json()["choices"][0]["message"]["content"].strip()

def ask_groq_large(prompt, system):
    return ask_groq(prompt, system, model="llama-3.3-70b-versatile")

def ask_groq_small(prompt, system):
    return ask_groq(prompt, system, model="llama-3.1-8b-instant")

def ask_groq_versatile(prompt, system):
    """Mixtral — different model, different rate limit bucket."""
    return ask_groq(prompt, system, model="qwen/qwen3-32b")

def ask_cerebras(prompt, system):
    if not CEREBRAS_KEY:
        raise Exception("No Cerebras key")
    for model in ["llama-3.3-70b", "llama3.3-70b", "llama3.1-8b"]:
        try:
            r = requests.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {CEREBRAS_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt}
                ], "max_tokens": 600},
                timeout=30
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise Exception("Cerebras: no working model")

def ask_cerebras_small(prompt, system):
    """Cerebras small model — separate rate limit."""
    if not CEREBRAS_KEY:
        raise Exception("No Cerebras key")
    r = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {CEREBRAS_KEY}", "Content-Type": "application/json"},
        json={"model": "llama3.1-8b", "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ], "max_tokens": 600},
        timeout=30
    )
    if r.status_code != 200:
        raise Exception("Cerebras small error: " + r.text[:80])
    return r.json()["choices"][0]["message"]["content"].strip()

# ── AGENT ROUTING ──────────────────────────────────────────────────────────────
# Spread 7 agents across 5 model slots to avoid rate limits
# Groq large + Groq small + Groq mixtral + Cerebras large + Cerebras small

AGENT_ROUTES = {
    "orchestrator": ask_cerebras,        # cerebras
    "intel":        ask_groq_small,       # groq small
    "analyst":      ask_groq_versatile,  # groq qwen
    "trader":       ask_cerebras_small,  # cerebras small
    "risk":         ask_cerebras,        # cerebras
    "income":       ask_groq_small,      # groq small
    "onchain":      ask_groq_small,      # groq small
    "security":     ask_cerebras,        # cerebras
}

FALLBACKS = [ask_groq_large, ask_cerebras, ask_groq_small, ask_groq_versatile]

def ask_ai(prompt, agent=None, system=None):
    if system is None:
        system = "You are BR0THA, a sharp crypto trading analyst. Be concise and data-driven."

    primary = AGENT_ROUTES.get(agent) if agent else ask_groq_large

    if primary:
        try:
            return primary(prompt, system)
        except Exception as e:
            print(f"  [AI] Primary failed for {agent}: {str(e)[:80]} — trying fallbacks")

    for fn in FALLBACKS:
        if fn == primary:
            continue
        try:
            time.sleep(1)
            return fn(prompt, system)
        except:
            continue

    return "ALL PROVIDERS FAILED"

if __name__ == "__main__":
    print("Testing working providers...")
    test = "Say OK in JSON: {\"status\": \"OK\"}"
    sys  = "Reply only in JSON."
    providers = {
        "Groq Large":     ask_groq_large,
        "Groq Small":     ask_groq_small,
        "Groq Mixtral":   ask_groq_versatile,
        "Cerebras Large": ask_cerebras,
        "Cerebras Small": ask_cerebras_small,
    }
    for name, fn in providers.items():
        try:
            r = fn(test, sys)
            print(f"  ✅ {name:20}: {r[:50]}")
        except Exception as e:
            print(f"  ❌ {name:20}: {str(e)[:60]}")
