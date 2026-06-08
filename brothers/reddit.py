import requests, sys, os, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import personality
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Reddit Brother"
DESCRIPTION = "Top posts from any subreddit — free, no key needed"
ENABLED     = True
COMMANDS    = ["reddit <subreddit>", "r/wallstreetbets", "reddit solana"]

TRIGGERS    = ["reddit", "r/", "subreddit"]

def _posts(sub: str, limit: int = 8) -> list:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news(f"reddit {sub}", max_results=limit))
        if not results:
            with DDGS() as ddgs:
                results = list(ddgs.text(f"reddit r/{sub} discussion", max_results=limit))
        return [{"title": r.get("title",""),
                 "score": 0,
                 "url":   r.get("url", r.get("href","")),
                 "comments": 0}
                for r in results]
    except Exception as e:
        print(f"  [reddit] {e}")
        return []

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    # Extract subreddit name
    sub = lower.replace("reddit", "").replace("r/", "").strip().split()[0] if lower.split() else ""
    if not sub:
        return "Give me a subreddit — e.g. 'reddit solana' or 'r/wallstreetbets'"

    posts = _posts(sub)
    if not posts:
        return f"❌ Could not fetch r/{sub} — may be private or not exist."

    lines = [f"🤖 r/{sub} — LATEST\n"]
    for p in posts[:6]:
        lines.append(f"  • {p['title']}")
        lines.append(f"    🔗 {p['url']}")

    result = "\n".join(lines)
    threading.Thread(target=personality.evolve,
        args=("reddit", f"fetched r/{sub}"), daemon=True).start()
    return result
