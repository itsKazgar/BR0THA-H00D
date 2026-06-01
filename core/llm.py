"""
LLM ROUTER — auto-picks the best available model
Priority: Local Ollama/Hermes → OpenRouter → Groq → Rule-based fallback
"""
import os, requests, json
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OR_URL   = "https://openrouter.ai/api/v1/chat/completions"
OR_MODEL = "deepseek/deepseek-r1-0528:free"

HERMES_MODELS = [
    "nous-hermes-2-mistral-7b",
    "nous-hermes-2-pro-llama3-8b",
    "hermes-3-llama3.1-8b",
]

def _check_ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code != 200:
            return None
        available = [m["name"] for m in r.json().get("models", [])]
        for preferred in HERMES_MODELS:
            for a in available:
                if preferred.lower() in a.lower():
                    return a
        for a in available:
            if "hermes" in a.lower() or "nous" in a.lower():
                return a
    except:
        pass
    return None

def _think_ollama(model, prompt, system=""):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 400}
    }, timeout=120)
    return r.json()["message"]["content"].strip()

def _think_openrouter(prompt, system=""):
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        return ""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = requests.post(OR_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": OR_MODEL,
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.3,
        }, timeout=20)
    data = r.json()
    if r.status_code != 200:
        raise Exception(f"status {r.status_code}: {data}")
    return data["choices"][0]["message"]["content"].strip()

def _think_groq(prompt, system=""):
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return ""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = requests.post(GROQ_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.3,
        }, timeout=15)
    data = r.json()
    if r.status_code != 200:
        raise Exception(f"status {r.status_code}: {data}")
    return data["choices"][0]["message"]["content"].strip()

def think(prompt, system=""):
    """
    Returns (response, source)
    Priority: Hermes → OpenRouter → Groq → rules
    """
    # 1. Local Hermes
    hermes_model = _check_ollama()
    if hermes_model:
        try:
            resp = _think_ollama(hermes_model, prompt, system)
            if resp:
                return resp, f"hermes/{hermes_model.split(':')[0]}"
        except Exception as e:
            print(f"  [llm] ollama error: {e} — falling back")

    # 2. OpenRouter
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            resp = _think_openrouter(prompt, system)
            if resp:
                return resp, "openrouter/deepseek"
        except Exception as e:
            print(f"  [llm] openrouter error: {e} — falling back")

    # 3. Anthropic Claude
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            key = os.getenv("ANTHROPIC_API_KEY")
            messages = []
            if system:
                messages.append({"role": "user", "content": f"[system] {system}"})
            messages.append({"role": "user", "content": prompt})
            r = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5",
                      "max_tokens": 400,
                      "messages": messages},
                timeout=20)
            if r.status_code == 200:
                resp = r.json()["content"][0]["text"].strip()
                if resp:
                    return resp, "anthropic/claude"
        except Exception as e:
            print(f"  [llm] anthropic error: {e} — falling back")

    # 4. OpenAI
    if os.getenv("OPENAI_API_KEY"):
        try:
            key = os.getenv("OPENAI_API_KEY")
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            r = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "gpt-4o-mini",
                      "messages": msgs,
                      "max_tokens": 400},
                timeout=20)
            if r.status_code == 200:
                resp = r.json()["choices"][0]["message"]["content"].strip()
                if resp:
                    return resp, "openai/gpt4o-mini"
        except Exception as e:
            print(f"  [llm] openai error: {e} — falling back")

    # 5. Groq
    if os.getenv("GROQ_API_KEY"):
        try:
            resp = _think_groq(prompt, system)
            if resp:
                return resp, "groq/llama3"
        except Exception as e:
            print(f"  [llm] groq error: {e} — falling back")

    # 4. Rules fallback
    return "", "rules"

def status():
    hermes = _check_ollama()
    if hermes:
        return f"🟣 Local Hermes ({hermes.split(':')[0]})"
    if os.getenv("OPENROUTER_API_KEY"):
        return "🟠 OpenRouter/DeepSeek"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "🔵 Anthropic/Claude"
    if os.getenv("OPENAI_API_KEY"):
        return "🟢 OpenAI/GPT4o-mini"
    if os.getenv("GROQ_API_KEY"):
        return "🟡 Groq llama3"
    return "⚪ Rule-based (no LLM)"
