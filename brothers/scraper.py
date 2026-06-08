import os, requests, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import re
from core import personality
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Scraper Brother"
DESCRIPTION = "Reads any URL and summarizes the content"
ENABLED     = True
COMMANDS    = ["scrape <url>", "read <url>"]

def run(user_input):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in ["scrape ", "read url ", "read http", "summarize http"]):
        return None
    url = user_input.split(" ", 1)[1].strip()
    if not url.startswith("http"):
        return None
    try:
        r    = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        text = re.sub(r'<script[^>]*>.*?</script>', '', r.text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>',  '', text,   flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()[:4000]
        key  = os.getenv("GROQ_API_KEY", "")
        if key and len(text) > 300:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": 600,
                      "messages": [{"role": "user", "content":
                          f"Summarize in 4 bullet points:\n\n{text}"}]},
                timeout=15)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        return text[:1000]
    except Exception as e:
        return f"Could not read {url}: {e}"
