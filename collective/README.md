# Collective 🤖
> Solana AI trading dashboard powered by a multi-model agent council

**🔴 Live Demo:** https://itskazgar.github.io/collective

A modular AI trading system where multiple AI models (Claude, GPT-4o, Grok, Gemini, Groq) vote on trades together. The council reaches consensus before any swap executes.

## Features
- 🧠 Multi-AI council voting system — any provider, any model
- ⇄ Jupiter v6 swap aggregator for best Solana prices
- 🐋 Whale wallet scanner
- 📊 Live market data — CoinGecko, DexScreener, pump.fun
- 🔑 API keys stay in your browser — never touch the server
- 🚀 One-click deploy to Railway or Render (free)

## Stack
| Layer | Tech |
|-------|------|
| Dashboard | HTML/JS — deploy to Netlify |
| API | FastAPI (api.py) — deploy to Render/Railway |
| AI Providers | Claude, GPT-4o, Grok, Gemini, Groq, OpenRouter |
| Blockchain | Solana — Jupiter v6, Helius RPC |

## Run locally
```bash
git clone https://github.com/itsKazgar/collective
cd collective
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn brotha_api:app --host 0.0.0.0 --port 8000
```

Then open `dashboard.html` in your browser and connect to `http://localhost:8000`.

## Deploy free
- **API** → [Railway.app](https://railway.app) or [Render.com](https://render.com)
- **Dashboard** → [Netlify](https://netlify.com) drag and drop the HTML file

## Environment variables
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GROK_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
HELIUS_API_KEY=
WALLET_PRIVATE_KEY_B58=
