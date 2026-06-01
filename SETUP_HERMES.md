# 🟣 Enable Local Hermes AI (Free, No API Key)

## Requirements
- 8GB+ RAM
- Linux/Mac (Windows: use WSL2)

## Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

## Pull Hermes model (pick based on your RAM)
```bash
# 8GB RAM
ollama pull nous-hermes-2-mistral-7b

# 16GB RAM (better)  
ollama pull nous-hermes-2-pro-llama3-8b

# 32GB RAM (best)
ollama pull hermes-3-llama3.1-8b
```

## Start Ollama (runs in background)
```bash
ollama serve &
```

## Run BR0THER-H00D
```bash
python start.py
```

The system auto-detects Hermes and uses it. No config needed.
The banner will show 🟣 Local Hermes when active.

## Priority order
1. 🟣 Local Hermes (best — free, private, fast reasoning)
2. 🟡 Groq API (good — needs GROQ_API_KEY in .env)
3. ⚪ Rule-based (works — no AI, uses scoring only)
