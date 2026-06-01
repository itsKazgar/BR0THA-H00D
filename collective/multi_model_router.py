import os, asyncio, aiohttp, time, json, sqlite3, logging
from dotenv import load_dotenv
load_dotenv("/home/kazgar/BR0THA_bot/.env")

logger = logging.getLogger(__name__)

OR_KEY  = os.getenv("OPENROUTER_API_KEY", "")
DB_PATH = os.getenv("DB_PATH", "/home/kazgar/BR0THA_bot/brotha.db")
OR_URL  = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "default":   os.getenv("MODEL_DEFAULT",  "anthropic/claude-sonnet-4-5"),
    "grok":      os.getenv("MODEL_GROK",     "x-ai/grok-beta"),
    "gemini":    os.getenv("MODEL_GEMINI",   "google/gemini-flash-1.5"),
    "deepseek":  os.getenv("MODEL_DEEPSEEK", "deepseek/deepseek-chat"),
    "groq":      os.getenv("MODEL_GROQ",     "meta-llama/llama-3.1-8b-instruct:free"),
    "kimi":      os.getenv("MODEL_KIMI",     "moonshot-v1-128k"),
}

ROUTING_RULES = [
    (["twitter","crypto twitter"," ct ","tweet","trending","alpha","whale","kol","grok"], "grok"),
    (["latest","right now","today","news","current","what happened","search","look up"], "gemini"),
    (["calculate","code","script","function","debug","error","math","solve","reason"], "deepseek"),
    (["quick","fast","short answer","one liner","just tell me","briefly"], "groq"),
    (["summarize this","read this","tldr","long doc","full context","paste"], "kimi"),
]

def route_model(text: str, agent: str = "assistant") -> str:
    if agent == "trader":  return "deepseek"
    if agent == "intel":   return "grok"
    t = text.lower()
    for keywords, model in ROUTING_RULES:
        if any(k in t for k in keywords):
            return model
    return "default"

async def call_model(model_key: str, messages: list, system: str = "", max_tokens: int = 1024) -> str:
    if not OR_KEY:
        return "[OPENROUTER_API_KEY not set]"
    model_id = MODELS.get(model_key, MODELS["default"])
    payload = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": ([{"role":"system","content":system}] + messages) if system else messages,
    }
    headers = {
        "Authorization": f"Bearer {OR_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/BR0THA_bot",
        "X-Title": "BR0THA",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(OR_URL, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status != 200:
                    err = await r.text()
                    return f"[{model_key} error {r.status}: {err[:100]}]"
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()
    except asyncio.TimeoutError:
        return f"[{model_key} timed out]"
    except Exception as e:
        return f"[{model_key} failed: {e}]"

def get_shared_context(limit: int = 5) -> str:
    try:
        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute("SELECT topic, insight FROM bot_learnings ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        if not rows: return ""
        return "\n[SHARED BRAIN]\n" + "\n".join(f"- {t}: {i}" for t,i in rows) + "\n"
    except: return ""

def write_shared_context(topic: str, insight: str, source: str = "model"):
    try:
        with sqlite3.connect(DB_PATH) as db:
            db.execute("INSERT INTO bot_learnings (topic,insight,confidence,source) VALUES (?,?,?,?)",
                       (topic[:120], insight[:500], 0.7, source))
    except: pass

def log_collab(user_id, prompt, model_used, response):
    try:
        with sqlite3.connect(DB_PATH) as db:
            db.execute("INSERT INTO ai_collab_log (user_id,prompt,final_response,models_used) VALUES (?,?,?,?)",
                       (str(user_id), prompt[:1000], response[:2000], model_used))
    except: pass

async def smart_ask(text: str, user_id=None, agent: str = "assistant",
                    system_override: str = "", history: list = None, max_tokens: int = 1024) -> str:
    chosen  = route_model(text, agent)
    system  = system_override or (
        "You are BR0THA — sharp, no-BS Solana/crypto AI. "
        "Speak directly, use a bit of slang, get to the point. Never be cringe."
    )
    system += get_shared_context()
    messages = (history or []) + [{"role":"user","content":text}]
    reply = await call_model(chosen, messages, system=system, max_tokens=max_tokens)
    if reply.startswith("["):
        reply = await call_model("default", messages, system=system, max_tokens=max_tokens)
        chosen += "+fallback"
    log_collab(user_id, text, chosen, reply)
    if hash(text) % 5 == 0 and len(reply) > 80:
        write_shared_context(text[:60], reply[:200], source=chosen)
    return reply

if __name__ == "__main__":
    async def health():
        print("Testing all models via OpenRouter...\n")
        for name in MODELS:
            t0 = time.time()
            r = await call_model(name, [{"role":"user","content":"say 'online' in 3 words"}], max_tokens=20)
            ms = int((time.time()-t0)*1000)
            icon = "✅" if not r.startswith("[") else "❌"
            print(f"  {icon}  {name:12}  {ms:4}ms  {r[:60]}")
    asyncio.run(health())
