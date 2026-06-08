import requests, sys, os, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, personality

NAME        = "HackerNews Brother"
DESCRIPTION = "Top HN stories — builders, startups, tech, real signal"
ENABLED     = True
COMMANDS    = ["hn", "hacker news", "hn top", "hn ask", "hn show"]

TRIGGERS    = ["hn", "hacker news", "hackernews", "show hn", "ask hn"]

def _top(limit=10, mode="top") -> list:
    try:
        url = f"https://hacker-news.firebaseio.com/v0/{mode}stories.json"
        ids = requests.get(url, timeout=6).json()[:limit]
        stories = []
        for sid in ids:
            r = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=4).json()
            if r and r.get("title"):
                stories.append({
                    "title": r.get("title",""),
                    "url":   r.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "score": r.get("score", 0),
                    "comments": r.get("descendants", 0),
                })
        return stories
    except Exception as e:
        return []

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    mode = "show" if "show" in lower else "ask" if "ask" in lower else "top"
    stories = _top(limit=8, mode=mode)
    if not stories:
        return "❌ Could not fetch HN stories."

    lines = [f"🟠 HACKER NEWS — {mode.upper()}\n"]
    for s in stories:
        lines.append(f"  • {s['title']}")
        lines.append(f"    ⬆️  {s['score']} pts | 💬 {s['comments']} | {s['url']}")
    
    result = "\n".join(lines)
    from core import council
    council.inscribe("hn", f"HN {mode}: {stories[0]['title']} | {stories[1]['title'] if len(stories)>1 else ''}", signal_type="intel")
    threading.Thread(target=personality.evolve,
        args=("hn", f"fetched HN {mode}: {stories[0]['title']}"), daemon=True).start()
    return result
