import psutil
import subprocess
import json

TIERS = {
    "free": [
        {"name": "tinyllama",        "min_ram_gb": 2,  "label": "TinyLlama 1.1B"},
        {"name": "phi3:mini",         "min_ram_gb": 4,  "label": "Phi-3 Mini"},
        {"name": "mistral",           "min_ram_gb": 6,  "label": "Mistral 7B"},
        {"name": "llama3:8b",         "min_ram_gb": 8,  "label": "Llama 3 8B"},
        {"name": "llama3:70b",        "min_ram_gb": 40, "label": "Llama 3 70B"},
    ],
    "api": [
        {"name": "claude-haiku",      "key_env": "ANTHROPIC_API_KEY",  "label": "Claude Haiku"},
        {"name": "claude-sonnet",     "key_env": "ANTHROPIC_API_KEY",  "label": "Claude Sonnet"},
        {"name": "gpt-4o-mini",       "key_env": "OPENAI_API_KEY",     "label": "GPT-4o Mini"},
        {"name": "gpt-4o",            "key_env": "OPENAI_API_KEY",     "label": "GPT-4o"},
        {"name": "groq-llama3",       "key_env": "GROQ_API_KEY",       "label": "Groq Llama3"},
    ],
    "ultra": [
        {"name": "cerebras-llama3",   "key_env": "CEREBRAS_API_KEY",   "label": "Cerebras Llama3 (fast)"},
    ]
}

def get_free_ram_gb():
    mem = psutil.virtual_memory()
    return round(mem.available / (1024 ** 3), 2)

def get_ollama_models():
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")[1:]
        return [line.split()[0] for line in lines if line.strip()]
    except Exception:
        return []

def get_env_keys():
    import os
    return {k: bool(v) for k, v in os.environ.items() if "API_KEY" in k}

def pick_best_model(prefer_tier=None):
    free_ram = get_free_ram_gb()
    ollama_installed = get_ollama_models()
    env_keys = get_env_keys()

    report = {
        "free_ram_gb": free_ram,
        "ollama_models": ollama_installed,
        "api_keys_found": [k for k, v in env_keys.items() if v],
        "selected": None,
        "tier": None,
        "reason": ""
    }

    if prefer_tier in (None, "free"):
        best_free = None
        for model in reversed(TIERS["free"]):
            if free_ram >= model["min_ram_gb"]:
                best_free = model
                break
        if best_free:
            name = best_free["name"]
            if name in ollama_installed:
                report["selected"] = name
                report["tier"] = "free"
                report["reason"] = f"{free_ram}GB RAM free → using {best_free['label']} (already pulled)"
                return report
            else:
                report["reason"] = f"{best_free['label']} fits RAM but not pulled yet. Run: ollama pull {name}"
                report["selected"] = name
                report["tier"] = "free"
                return report

    if prefer_tier in (None, "api"):
        for model in TIERS["api"]:
            key = model.get("key_env")
            if key and env_keys.get(key):
                report["selected"] = model["name"]
                report["tier"] = "api"
                report["reason"] = f"API key found for {model['label']}"
                return report

    if prefer_tier in (None, "ultra"):
        for model in TIERS["ultra"]:
            key = model.get("key_env")
            if key and env_keys.get(key):
                report["selected"] = model["name"]
                report["tier"] = "ultra"
                report["reason"] = f"Ultra key found: {model['label']}"
                return report

    report["reason"] = "No model available. Install Ollama (free) or add an API key."
    return report

def print_status():
    result = pick_best_model()
    print("\n╔══════════════════════════════════════════╗")
    print("║        BR0THER-H00D  Model Router        ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  RAM free   : {result['free_ram_gb']} GB")
    print(f"║  Tier       : {result['tier'] or 'none'}")
    print(f"║  Model      : {result['selected'] or 'none'}")
    print(f"║  Reason     : {result['reason']}")
    print(f"║  Ollama     : {', '.join(result['ollama_models']) or 'none pulled'}")
    print(f"║  API keys   : {', '.join(result['api_keys_found']) or 'none'}")
    print("╚══════════════════════════════════════════╝\n")
    return result

if __name__ == "__main__":
    print_status()
