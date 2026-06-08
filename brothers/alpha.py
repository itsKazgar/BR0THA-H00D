import os, requests, sys, threading
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import personality

NAME        = "Alpha Brother"
DESCRIPTION = "Tech alpha — AI releases, YC launches, builder news, startup stuff"
ENABLED     = True
COMMANDS    = ["alpha", "tech", "ai news", "yc", "startups", "builders"]

TRIGGERS = ["what launched", "what shipped", "show me alpha", "hacker news", "hn ", "product hunt","alpha", "tech news", "ai news", "what's new in ai", "yc",
            "startups", "builders", "what dropped", "new tools", "new ai"]

FEEDS = {
    "ai":         "latest AI tools models released",
    "yc":         "Y Combinator new startups launches",
    "tech":       "tech startups product launches this week",
    "builders":   "indie hackers new products launched this week",
    "hn":         "hacker news top stories startups tools",
    "longevity":  "longevity anti-aging research breakthrough",
    "peptides":   "peptide therapy research news",
    "biotech":    "new biotech health tech this week",
    "solana":     "Solana ecosystem news updates",
    "sol_people": "Solana founders builders Anatoly Yakovenko news",
}

def _fetch(query: str, max_results: int = 6) -> list:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results))
    except Exception as e:
        print(f"  [alpha] fetch failed: {e}")
        return []

def _summarize(topic: str, results: list) -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key or not results:
        return _format_raw(results)

    context = ""
    for r in results:
        title = r.get("title", "")
        body  = r.get("body", "")[:200]
        url   = r.get("url", "")
        context += f"- {title}: {body} ({url})\n"

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile", "max_tokens": 600,
                  "temperature": 0.2,
                  "messages": [{"role": "user", "content":
                      f"You brief a reader who already follows tech closely and "
                      f"has no patience for the obvious. Topic: {topic}.\n\n"
                      f"SOURCE MATERIAL (the only facts you may use):\n{context}\n\n"
                      f"Write the brief:\n"
                      f"- Lead with the single most important item, one line on why it matters.\n"
                      f"- Then 3-4 more items: what happened + the so-what, one line each.\n"
                      f"- Skip anything that is just a price move or a headline everyone saw.\n"
                      f"- Only state facts present in the source above. If inferring, "
                      f"say 'likely' or 'worth watching' — never invent numbers, dates, or quotes.\n"
                      f"- Report what happened and what to watch. Do not predict or give advice.\n"
                      f"- End each item with its URL. No preamble, no sign-off."}]},
            timeout=15)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [alpha] summarize failed: {e}")

    return _format_raw(results)

def _format_raw(results: list) -> str:
    if not results:
        return "No results found."
    lines = []
    for r in results:
        title = r.get("title", "")
        url   = r.get("url", "")
        body  = r.get("body", "")[:120]
        lines.append(f"• {title}\n  {body}\n  {url}")
    return "\n\n".join(lines)

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    # Pick the right feed based on what they asked
    if any(x in lower for x in ["yc", "y combinator", "startup"]):
        topic, query = "YC & startups", FEEDS["yc"]
    elif any(x in lower for x in ["ai", "model", "tool", "dropped"]):
        topic, query = "AI & new tools", FEEDS["ai"]
    elif any(x in lower for x in ["builder", "indie", "product"]):
        topic, query = "builders & launches", FEEDS["builders"]
    else:
        topic, query = "tech alpha", FEEDS["tech"]

    results = _fetch(query)
    if not results:
        return "Couldn't fetch alpha right now."

    summary = _summarize(topic, results)
    # Evolve personality in background — non-blocking
    from core import council
    council.inscribe("alpha", f"{topic}: {summary[:200]}", signal_type="intel")
    threading.Thread(target=personality.evolve, args=("alpha", f"{user_input} -> {summary[:150]}"), daemon=True).start()
    return f"⚡ ALPHA — {topic.upper()}\n\n{summary}"
