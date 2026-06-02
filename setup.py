#!/usr/bin/env python3
"""
BR0THER-H00D — AI Setup Wizard
Supports every major AI provider.
"""
import os, sys, requests, subprocess
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'
BD='\033[1m'; DM='\033[2m'; RS='\033[0m'

def banner():
    print(f"""
{CY}{BD}╔══════════════════════════════════════════════════════╗
║   🤖 BR0THER-H00D — AI Setup Wizard                 ║
║   Add any AI to power your trading agents           ║
╚══════════════════════════════════════════════════════╝{RS}
""")

def save_key(key_name, value):
    """Save key to .env file."""
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w").close()
    set_key(ENV_PATH, key_name, value)

def get_current(key_name):
    val = os.getenv(key_name, "")
    if val and val != "your_key_here":
        return val[:8] + "..." 
    return None

def test_openrouter(key):
    """Test OpenRouter and find best available free model."""
    free_models = [
        "deepseek/deepseek-v4-flash:free",
        "moonshotai/kimi-k2.6:free",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
    ]
    for model in free_models:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model,
                      "messages": [{"role":"user","content":"say ok"}],
                      "max_tokens": 5},
                timeout=15)
            if r.status_code == 200:
                return True, model
        except:
            continue
    return False, None

def test_groq(key):
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama3-8b-8192",
                  "messages": [{"role":"user","content":"say ok"}],
                  "max_tokens": 5},
            timeout=10)
        return r.status_code == 200
    except:
        return False

def test_anthropic(key):
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key,
                     "anthropic-version": "2023-06-01"},
            json={"model": "claude-haiku-4-5",
                  "max_tokens": 5,
                  "messages": [{"role":"user","content":"say ok"}]},
            timeout=10)
        return r.status_code == 200
    except:
        return False

def test_openai(key):
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "gpt-4o-mini",
                  "messages": [{"role":"user","content":"say ok"}],
                  "max_tokens": 5},
            timeout=10)
        return r.status_code == 200
    except:
        return False

def test_cerebras(key):
    try:
        r = requests.post("https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama3.1-8b",
                  "messages": [{"role":"user","content":"say ok"}],
                  "max_tokens": 5},
            timeout=10)
        return r.status_code == 200
    except:
        return False

def test_ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            hermes = [m for m in models if "hermes" in m.lower() or "nous" in m.lower()]
            return True, hermes
    except:
        pass
    return False, []

def setup_provider(name, key_name, test_fn, get_url, free=False):
    current = get_current(key_name)
    status = f"{GR}✅ configured ({current}){RS}" if current else f"{DM}not set{RS}"
    free_tag = f" {GR}[FREE]{RS}" if free else ""
    
    print(f"\n{BD}{name}{RS}{free_tag} — {status}")
    print(f"  Get key: {DM}{get_url}{RS}")
    
    choice = input(f"  Add/update key? (y/n/skip) [{DM}n{RS}]: ").strip().lower()
    if choice != "y":
        return current is not None

    key = input(f"  Paste your {name} key: ").strip()
    if not key:
        print(f"  {YL}Skipped{RS}")
        return False

    print(f"  Testing...", end=" ", flush=True)
    if callable(test_fn):
        ok = test_fn(key)
    else:
        ok = True

    if ok:
        save_key(key_name, key)
        print(f"{GR}✅ works!{RS}")
        return True
    else:
        print(f"{RD}❌ key test failed — check the key and try again{RS}")
        retry = input("  Save anyway? (y/n): ").strip().lower()
        if retry == "y":
            save_key(key_name, key)
            return True
        return False

def setup_openrouter():
    current = get_current("OPENROUTER_API_KEY")
    status = f"{GR}✅ configured ({current}){RS}" if current else f"{DM}not set{RS}"
    
    print(f"\n{BD}OpenRouter{RS} {GR}[FREE TIER]{RS} — {status}")
    print(f"  Access: Claude, DeepSeek, Kimi, Gemini, Llama and 100+ models")
    print(f"  Get key: {DM}https://openrouter.ai/keys{RS}")
    
    choice = input(f"  Add/update key? (y/n) [{DM}n{RS}]: ").strip().lower()
    if choice != "y":
        return current is not None

    key = input("  Paste your OpenRouter key: ").strip()
    if not key:
        return False

    print("  Testing and finding best free model...", end=" ", flush=True)
    ok, best_model = test_openrouter(key)
    
    if ok:
        save_key("OPENROUTER_API_KEY", key)
        save_key("OR_MODEL", best_model)
        print(f"{GR}✅ works! Best model: {best_model}{RS}")
        return True
    else:
        print(f"{YL}⚠️  key valid but free models rate limited right now{RS}")
        save_key("OPENROUTER_API_KEY", key)
        print(f"  {GR}Key saved{RS} — will work when models are available")
        return True

def setup_ollama():
    print(f"\n{BD}Local Hermes/Ollama{RS} {GR}[100% FREE — runs on your machine]{RS}")
    print(f"  Best option for privacy. Needs 8GB+ RAM.")
    
    ok, models = test_ollama()
    if ok and models:
        print(f"  {GR}✅ Ollama running! Hermes models found: {', '.join(models)}{RS}")
        return True
    elif ok:
        print(f"  {YL}⚠️  Ollama running but no Hermes model found{RS}")
        print(f"  Run: {BD}ollama pull nous-hermes-2-mistral-7b{RS}")
    else:
        print(f"  {DM}Ollama not running{RS}")
        install = input("  Install Ollama now? (y/n): ").strip().lower()
        if install == "y":
            print("  Installing...")
            os.system("curl -fsSL https://ollama.com/install.sh | sh")
            print(f"\n  Now run: {BD}ollama pull nous-hermes-2-mistral-7b{RS}")
            print(f"  Then:    {BD}ollama serve &{RS}")
    return False

def setup_telegram():
    current_token = get_current("TELEGRAM_BOT_TOKEN")
    current_chat  = get_current("TELEGRAM_CHAT_ID")
    status = f"{GR}✅ configured{RS}" if current_token else f"{DM}not set{RS}"
    
    print(f"\n{BD}Telegram Alerts{RS} {GR}[FREE]{RS} — {status}")
    print(f"  Get trade alerts on your phone instantly")
    print(f"  1. Message @BotFather on Telegram → /newbot")
    print(f"  2. Message @userinfobot to get your chat ID")
    
    choice = input(f"  Set up Telegram? (y/n) [{DM}n{RS}]: ").strip().lower()
    if choice != "y":
        return

    token = input("  Bot token from BotFather: ").strip()
    chat_id = input("  Your chat ID: ").strip()
    
    if token and chat_id:
        save_key("TELEGRAM_BOT_TOKEN", token)
        save_key("TELEGRAM_CHAT_ID", chat_id)
        print(f"  {GR}✅ Telegram configured{RS}")

def setup_solana():
    print(f"\n{BD}Solana Wallet{RS}")
    print(f"  {DM}Needed for live trading. Paper mode works without a wallet.{RS}")
    print(f"\n  {BD}[1]{RS} Generate a new wallet automatically {GR}(recommended){RS}")
    print(f"  {BD}[2]{RS} Import existing private key {DM}(Phantom, etc){RS}")
    print(f"  {BD}[3]{RS} Skip — paper trading only")
    choice = input(f"\n  Choice (1/2/3) [3]: ").strip() or "3"

    if choice == "1":
        print(f"  {YL}Generating new Solana wallet...{RS}")
        try:
            from solders.keypair import Keypair
            import base58
            kp = Keypair()
            address = str(kp.pubkey())
            private_key = base58.b58encode(bytes(kp)).decode()
            save_key("WALLET_ADDRESS", address)
            save_key("WALLET_PRIVATE_KEY", private_key)
            print(f"\n  {GR}✅ New wallet created!{RS}")
            print(f"  {BD}Address:{RS}     {address}")
            print(f"  {BD}Private Key:{RS} {private_key}")
            print(f"  {RD}{BD}⚠️  Save your private key somewhere safe — shown only once!{RS}")
            rpc = input("  Solana RPC (leave blank for default): ").strip()
            if rpc: save_key("SOLANA_RPC", rpc)
        except ImportError:
            print(f"  {RD}❌ Missing: pip install solders base58{RS}")

    elif choice == "2":
        print(f"  {RD}{BD}WARNING: Never share your private key with anyone{RS}")
        print(f"  {DM}Export from Phantom: Settings > Security > Export Private Key{RS}")
        key = input("  Paste your private key (base58): ").strip()
        if key:
            try:
                from solders.keypair import Keypair
                import base58
                kp = Keypair.from_bytes(base58.b58decode(key))
                address = str(kp.pubkey())
                save_key("WALLET_ADDRESS", address)
                save_key("WALLET_PRIVATE_KEY", key)
                save_key("LIVE_MODE", "true")
                rpc = input("  Solana RPC (leave blank for default): ").strip()
                if rpc: save_key("SOLANA_RPC", rpc)
                print(f"  {GR}✅ Wallet imported: {address}{RS}")
                print(f"  {YL}⚠️  Test with small amounts first!{RS}")
            except Exception as e:
                print(f"  {RD}❌ Invalid key: {e}{RS}")
        else:
            print(f"  {YL}Skipped{RS}")

    else:
        print(f"  {YL}Skipped — paper trading mode{RS}")

def print_summary():
    load_dotenv(ENV_PATH, override=True)
    
    providers = {
        "Ollama/Hermes": test_ollama()[0],
        "OpenRouter":    bool(get_current("OPENROUTER_API_KEY")),
        "Groq":          bool(get_current("GROQ_API_KEY")),
        "Anthropic":     bool(get_current("ANTHROPIC_API_KEY")),
        "OpenAI":        bool(get_current("OPENAI_API_KEY")),
        "Cerebras":      bool(get_current("CEREBRAS_API_KEY")),
        "Telegram":      bool(get_current("TELEGRAM_BOT_TOKEN")),
        "Live Trading":  os.getenv("LIVE_MODE","").lower() == "true",
    }
    
    print(f"\n{CY}{BD}╔══════════════════════════════════════════════════════╗")
    print(f"║   🧠 YOUR SETUP SUMMARY                              ║")
    print(f"╠══════════════════════════════════════════════════════╣{RS}")
    
    for name, active in providers.items():
        icon = f"{GR}✅{RS}" if active else f"{DM}⬜{RS}"
        print(f"  {icon} {name}")
    
    # Show AI priority
    print(f"\n{BD}  AI Priority Order:{RS}")
    priority = []
    if test_ollama()[0]: priority.append("🟣 Local Hermes")
    if get_current("OPENROUTER_API_KEY"): priority.append("🟠 OpenRouter")
    if get_current("GROQ_API_KEY"): priority.append("🟡 Groq")
    if get_current("ANTHROPIC_API_KEY"): priority.append("🔵 Anthropic")
    if get_current("OPENAI_API_KEY"): priority.append("🟢 OpenAI")
    if get_current("CEREBRAS_API_KEY"): priority.append("⚡ Cerebras")
    priority.append("⚪ Rule-based")
    
    for i, p in enumerate(priority):
        arrow = "→" if i < len(priority)-1 else ""
        print(f"  {p} {arrow}", end=" ")
    print()
    
    print(f"\n{CY}{BD}╚══════════════════════════════════════════════════════╝{RS}")
    print(f"\n  Run {BD}python start.py{RS} to start trading!\n")

def main():
    banner()
    
    print(f"{BD}This wizard helps you connect AI providers to BR0THER-H00D.{RS}")
    print(f"Everything is optional — the system works without any keys.")
    print(f"\n{YL}Press Enter to skip any provider.{RS}\n")
    
    input(f"Press {BD}Enter{RS} to start setup...")

    # Free providers first
    print(f"\n{GR}{BD}━━━ FREE AI PROVIDERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RS}")
    setup_ollama()
    setup_openrouter()
    setup_provider(
        "Groq (Llama3 — fast & free)",
        "GROQ_API_KEY",
        test_groq,
        "https://console.groq.com",
        free=True
    )

    # Paid providers
    print(f"\n{YL}{BD}━━━ PAID AI PROVIDERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RS}")
    setup_provider(
        "Anthropic (Claude — best reasoning)",
        "ANTHROPIC_API_KEY",
        test_anthropic,
        "https://console.anthropic.com"
    )
    setup_provider(
        "OpenAI (GPT-4o)",
        "OPENAI_API_KEY",
        test_openai,
        "https://platform.openai.com/api-keys"
    )
    setup_provider(
        "Cerebras (ultra fast inference)",
        "CEREBRAS_API_KEY",
        test_cerebras,
        "https://cloud.cerebras.ai"
    )

    # Other setup
    print(f"\n{CY}{BD}━━━ OTHER SETUP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RS}")
    setup_telegram()
    setup_solana()
    setup_wallet()

    # Summary
    print_summary()

if __name__ == "__main__":
    main()
