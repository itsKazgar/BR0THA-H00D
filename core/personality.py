"""
PERSONALITY — Each brother develops their own voice over time.
Stored in brain state, evolves after every interaction.
"""
import os, requests, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain

# Seed personalities — starting point, will drift over time
SEEDS = {
    "alpha":       "curious, plugged in, spots signals early, gets hyped about the right things, talks like a smart friend texting you",
    "search":      "thorough, direct, no fluff, cites sources, slightly nerdy",
    "crypto":      "market-aware, calm under volatility, reads charts like a language, occasional degen energy",
    "briefing":    "sharp morning energy, gets to the point fast, like a good trader's daily standup",
    "portfolio":   "analytical, honest about losses, tracks everything, no sugarcoating",
    "scraper":     "curious reader, good at finding the buried lede, summarizes without losing the signal",
    "orchestrator":"sees the big picture, delegates cleanly, connects dots across domains",
}

def get(brother_id: str) -> str:
    """Load this brother's current personality, or return seed if new."""
    state = brain.load_state(f"personality_{brother_id}")
    if state and state.get("traits"):
        return state["traits"]
    return SEEDS.get(brother_id, "helpful, direct, no fluff")

def evolve(brother_id: str, interaction: str):
    """
    After an interaction, subtly evolve the personality traits.
    Happens async — won't slow down responses.
    """
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return

    current = get(brother_id)

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile", "max_tokens": 100,
                  "temperature": 0.9,
                  "messages": [{"role": "user", "content":
                      f"A brother AI named '{brother_id}' has these personality traits:\n"
                      f'"{current}"\n\n'
                      f"They just had this interaction:\n{interaction[:300]}\n\n"
                      f"Subtly evolve their traits based on what happened. "
                      f"Small drift only — maybe one new quirk, emphasis shift, or new interest. "
                      f"Keep it under 20 words. Return ONLY the updated trait string, nothing else."}]},
            timeout=10)
        if r.status_code == 200:
            new_traits = r.json()["choices"][0]["message"]["content"].strip().strip('"')
            if 5 < len(new_traits) < 300:
                brain.save_state(f"personality_{brother_id}", {
                    "traits": new_traits,
                    "evolved_from": current,
                    "interaction_count": brain.load_state(f"personality_{brother_id}").get("interaction_count", 0) + 1
                })
    except Exception as e:
        print(f"  [personality] evolve failed: {e}")

def inject(brother_id: str) -> str:
    """Returns a system prompt snippet to inject into any brother's LLM call."""
    traits = get(brother_id)
    count  = brain.load_state(f"personality_{brother_id}").get("interaction_count", 0)
    return f"Your personality (evolved over {count} interactions): {traits}"
