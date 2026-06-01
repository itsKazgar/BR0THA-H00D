import os
import requests

CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY", "")

URL = "https://api.cerebras.ai/v1/chat/completions"

def ask_cerebras(prompt: str):
    if not CEREBRAS_KEY:
        return "[CEREBRAS_API_KEY not set]"

    headers = {
        "Authorization": f"Bearer {CEREBRAS_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "gpt-oss-120b",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 200
    }

    try:
        r = requests.post(URL, json=payload, headers=headers, timeout=30)

        if r.status_code != 200:
            return f"[CEREBRAS_ERROR {r.status_code}: {r.text[:200]}]"

        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"[CEREBRAS_EXCEPTION: {e}]"
