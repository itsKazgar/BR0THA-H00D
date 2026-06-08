import os, requests, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import personality
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Search Brother"
DESCRIPTION = "Real web & news search via DuckDuckGo + AI summary"
ENABLED     = True
COMMANDS    = ["search <query>", "find <query>", "news <topic>", "what is <topic>"]

TRIGGERS = ["search ", "google ", "find ", "news ", "what is ", "who is ",
            "how to ", "explain ", "tell me about ", "research "]

def _ddg_search(query: str, mode: str = "news", max_results: int = 6) -> list:
    """Fetch real results from DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            if mode == "news":
                return list(ddgs.news(query, max_results=max_results))
            else:
                return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"  [search] DDG failed: {e}")
        return []

def _summarize(query: str, results: list) -> str:
    """Use Groq to summarize real search results."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key or not results:
        return _format_raw(results)

    # Build context from real results
    context = ""
    for r in results:
        title = r.get("title", "")
        body  = r.get("body", r.get("snippet", ""))[:200]
        url   = r.get("url", r.get("href", ""))
        context += f"- {title}: {body} ({url})\n"

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile", "max_tokens": 500,
                  "temperature": 0.2,
                  "messages": [{"role": "user", "content":
                      f"User asked: {query}\n\n"
                      f"SOURCE RESULTS (the only facts you may use):\n{context}\n\n"
                      f"Answer the question directly using only the results above.\n"
                      f"- Lead with the actual answer, not a preamble.\n"
                      f"- Use only facts present in the results. If they don't fully "
                      f"answer it, say what's known and what isn't — never fill gaps "
                      f"from memory or invent numbers, dates, or quotes.\n"
                      f"- If sources disagree, say so.\n"
                      f"- Report what the sources say. Don't predict or advise.\n"
                      f"- Cite the source URL for each key claim. Keep it tight."}]},
            timeout=15)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [search] summarize failed: {e}")

    return _format_raw(results)

def _format_raw(results: list) -> str:
    """Fallback: just format results directly without LLM."""
    if not results:
        return "No results found."
    lines = []
    for r in results:
        title = r.get("title", "No title")
        url   = r.get("url", r.get("href", ""))
        body  = r.get("body", r.get("snippet", ""))[:150]
        lines.append(f"• {title}\n  {body}\n  {url}")
    return "\n\n".join(lines)

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    # Pick mode: news for market/crypto queries, text for general
    news_keywords = ["news", "market", "crypto", "bitcoin", "solana", "price",
                     "today", "latest", "crash", "pump", "dump", "trend"]
    mode = "news" if any(k in lower for k in news_keywords) else "text"

    results = _ddg_search(user_input, mode=mode)
    if not results:
        # fallback to text search if news came up empty
        results = _ddg_search(user_input, mode="text")
    if not results:
        return "No results found."

    result = _summarize(user_input, results)
    from core import council
    council.inscribe("search", f"searched: {user_input} | {result[:150]}", signal_type="intel")
    threading.Thread(target=personality.evolve, args=("search", f"{user_input} -> {result[:150]}"), daemon=True).start()
    return result
