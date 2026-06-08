"""
BR0THER ASSISTANT — Personal AI assistant mode
Uses the same brain/memory as the trader so it knows your history.
Supports: research, drafting, tasks, reminders, crypto checks, general help.
"""
import os, sys, time, requests, json
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, llm

CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'
BD='\033[1m';  DM='\033[2m';  RS='\033[0m';  MG='\033[95m'

HISTORY_LIMIT = 20  # conversation turns kept in context

def get_sol_price():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=6)
        return float(r.json()["solana"]["usd"])
    except:
        return None

def get_token_price(symbol):
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search?q={symbol}",
            timeout=8)
        pairs = [p for p in r.json().get("pairs", [])
                 if p.get("chainId") == "solana"
                 and p.get("baseToken", {}).get("symbol", "").upper() == symbol.upper()]
        if not pairs:
            return None
        best = sorted(pairs,
            key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0),
            reverse=True)[0]
        return {
            "symbol": symbol.upper(),
            "price":  float(best.get("priceUsd", 0) or 0),
            "change_1h": float(best.get("priceChange", {}).get("h1", 0) or 0),
            "change_24h": float(best.get("priceChange", {}).get("h24", 0) or 0),
            "mcap":   float(best.get("marketCap", 0) or 0),
            "liq":    float(best.get("liquidity", {}).get("usd", 0) or 0),
            "url":    best.get("url", ""),
        }
    except:
        return None

def get_coingecko_price(coin_id):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true",
            timeout=6)
        data = r.json().get(coin_id, {})
        return {
            "price": data.get("usd", 0),
            "change_24h": data.get("usd_24h_change", 0),
        }
    except:
        return None

def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        d = r.json()["data"][0]
        return f"{d['value']} ({d['value_classification']})"
    except:
        return None

def load_trader_context():
    """Pull trading state into context so assistant knows your portfolio."""
    mode = os.getenv("TRADE_MODE", "paper").lower()
    key  = "trader_live" if mode == "live" else "trader_paper"
    s    = brain.load_state(key)
    if not s:
        return "No trading data found."
    bal  = s.get("balance", 0)
    pnl  = s.get("total_pnl", 0)
    pos  = s.get("positions", {})
    hist = s.get("history", [])
    wins = sum(1 for t in hist if t.get("pnl_pct", 0) > 0)
    wr   = f"{wins/len(hist)*100:.0f}%" if hist else "n/a"
    pos_str = ", ".join([p["name"] for p in pos.values()]) if pos else "none"
    return (f"Trading balance: ${bal:.2f} | PnL: ${pnl:+.2f} | "
            f"Win rate: {wr} | Open positions: {pos_str} | "
            f"Total trades: {len(hist)}")

def build_system_prompt():
    trader_ctx = load_trader_context()
    memories   = brain.recall(limit=10)
    mem_str    = " | ".join([m["content"][:60] for m in memories[:5]]) if memories else "none"
    return f"""You are BR0THER, a sharp personal AI assistant and crypto trading companion.
You help with: research, drafting emails/messages, tasks, reminders, calculations, 
crypto analysis, general questions, and anything the user needs.

Current trader state: {trader_ctx}
Recent memory: {mem_str}
Current time: {datetime.now().strftime("%Y-%m-%d %H:%M")}

Be concise, direct, and practical. Use emojis sparingly. 
If asked about prices, say you'll check live data.
Remember context from earlier in the conversation."""

def handle_special_commands(user_input: str) -> str | None:
    # Check tool commands first
    try:
        from agents import assistant_tools
        tool_result = assistant_tools.handle_tool_command(user_input)
        if tool_result is not None:
            return tool_result
    except Exception as e:
        pass
    handle_special_commands
    """Handle built-in commands that don't need LLM."""
    inp = user_input.strip().lower()

    # Price checks
    if inp in ["sol", "solana", "sol price", "price sol"]:
        p = get_sol_price()
        return f"◎ SOL: ${p:,.2f}" if p else "Could not fetch SOL price."

    if inp.startswith("price "):
        symbol = inp.replace("price ", "").strip().upper()
        # Try major coins via CoinGecko first
        cg_map = {"BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
                  "SOL": "solana", "DOGE": "dogecoin", "PEPE": "pepe"}
        if symbol in cg_map:
            d = get_coingecko_price(cg_map[symbol])
            if d:
                return (f"{symbol}: ${d['price']:,.4f}  "
                        f"24h: {d['change_24h']:+.1f}%")
        # Try DexScreener for Solana tokens
        d = get_token_price(symbol)
        if d:
            return (f"{d['symbol']}: ${d['price']:.8f}  "
                    f"1h: {d['change_1h']:+.1f}%  24h: {d['change_24h']:+.1f}%  "
                    f"mcap: ${d['mcap']:,.0f}\n  🔗 {d['url']}")
        return f"Could not find price for {symbol}."

    # Fear & greed
    if "fear" in inp or "greed" in inp or "market mood" in inp:
        fg = get_fear_greed()
        return f"Fear & Greed Index: {fg}" if fg else "Could not fetch fear & greed."

    # Trading stats
    if inp in ["stats", "my stats", "trading stats", "balance", "portfolio"]:
        return load_trader_context()

    # Memory / history
    if inp in ["memory", "what do you remember", "recall"]:
        mems = brain.recall(limit=10)
        if not mems:
            return "No memories yet."
        lines = [f"  • {m['content'][:80]}" for m in mems[:8]]
        return "Recent memories:\n" + "\n".join(lines)

    # Save a note
    if inp.startswith("remember ") or inp.startswith("note "):
        note = user_input.split(" ", 1)[1].strip()
        brain.remember("assistant", note, type="user_note", tags="note,user")
        return f"✅ Saved to memory: {note}"

    # Todo
    if inp.startswith("todo ") or inp.startswith("task "):
        task = user_input.split(" ", 1)[1].strip()
        brain.remember("assistant", f"TODO: {task}", type="todo", tags="todo,task")
        return f"✅ Task added: {task}"

    if inp in ["todos", "tasks", "my tasks", "my todos"]:
        todos = brain.recall(type="todo", limit=20)
        if not todos:
            return "No tasks saved."
        lines = [f"  • {t['content'].replace('TODO: ','')}" for t in todos]
        return "Your tasks:\n" + "\n".join(lines)

    # Help
    if inp in ["ai", "ai status", "which ai", "llm", "model"]:
        from core import llm
        current = llm.status()
        return f"""🧠 AI STATUS: {current}

Priority order (first key found wins):
  1. 🟣 Local Ollama/Hermes  — free, runs on your machine
  2. 🟠 OpenRouter           — OPENROUTER_API_KEY in .env
  3. 🔵 Anthropic Claude     — ANTHROPIC_API_KEY in .env
  4. 🟢 OpenAI GPT-4o-mini   — OPENAI_API_KEY in .env
  5. 🟡 Groq Llama3          — GROQ_API_KEY in .env
  6. ⚪ Rule-based           — no AI, logic only

To switch: add the key to your .env file and restart.
Free options: Groq (groq.com) or OpenRouter (openrouter.ai)"""

    if inp in ["brothers", "skills", "team", "agents"]:
        import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from brothers import list_all
        bros = list_all()
        lines = [f"  🤝 {b['name']} — {b['description']}\n     {', '.join(b['commands'])}" for b in bros]
        return f"👥 Brotherhood ({len(bros)} brothers loaded):\n\n" + "\n\n".join(lines)

    if inp in ["help", "commands", "?"]:
        return """Commands:
  price SOL / price PEPE    — live price check
  stats / portfolio          — your trading balance & stats
  fear / greed               — market sentiment index
  remember <note>            — save a note to memory
  todo <task>                — add a task
  todos                      — list your tasks
  memory                     — show recent memories
  clear                      — clear screen
  exit / quit                — leave assistant mode

Or just type anything — I'll help."""

    if inp in ["clear", "cls"]:
        os.system("clear")
        return None

    return None  # not a special command, send to LLM


class Assistant:
    def __init__(self):
        brain.init_db()
        self.conversation = []  # list of {role, content}
        self.llm_source   = "unknown"

    def chat(self, user_input: str) -> str:
        # Check brothers first (plug and play skills)
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from brothers import dispatch
            result, brother = dispatch(user_input)
            if result is not None:
                self.llm_source = brother
                return result
        except Exception as e:
            pass
        # Check tool commands first
        try:
            from agents import assistant_tools
            tool_result = assistant_tools.handle_tool_command(user_input)
            if tool_result is not None:
                return tool_result
        except Exception as e:
            pass
        # Check special commands first
        special = handle_special_commands(user_input)
        if special is not None:
            return special

        # Add to conversation history
        self.conversation.append({"role": "user", "content": user_input})

        # Keep history manageable
        if len(self.conversation) > HISTORY_LIMIT * 2:
            self.conversation = self.conversation[-HISTORY_LIMIT * 2:]

        # Build full prompt with history
        history_str = ""
        for turn in self.conversation[:-1]:
            role = "You" if turn["role"] == "assistant" else "User"
            history_str += f"{role}: {turn['content']}\n"

        prompt = f"{history_str}User: {user_input}\nAssistant:"
        system = build_system_prompt()

        # Call LLM
        response, source = llm.think(prompt, system=system)
        self.llm_source = source

        if not response:
            response = "I couldn't process that right now. Try again or check your AI config."

        # Save to conversation
        self.conversation.append({"role": "assistant", "content": response})

        # Save important exchanges to brain memory
        if any(w in user_input.lower() for w in
               ["remember", "save", "note", "important", "todo", "remind"]):
            brain.remember("assistant",
                f"User asked: {user_input[:100]}",
                type="assistant_memory", tags="assistant,user")

        return response

    def run(self):
        os.system("clear")
        sol_price = get_sol_price()
        fg        = get_fear_greed()
        trader_ctx = load_trader_context()

        print(f"""
{MG}{BD}╔══════════════════════════════════════════════╗
║  🤖 BR0THER ASSISTANT                        ║
╠══════════════════════════════════════════════╣{RS}
  {DM}🧠 AI      {RS}  {llm.status()}
  {DM}💰 Trader  {RS}  {trader_ctx[:50]}
  {DM}◎  SOL     {RS}  {'${:,.2f}'.format(sol_price) if sol_price else 'unknown'}
  {DM}😨 Market  {RS}  {fg if fg else 'unknown'}
{MG}{BD}╠══════════════════════════════════════════════╣{RS}
  Type {BD}help{RS} for commands, or just ask anything.
  Type {BD}exit{RS} to go back.
{MG}{BD}╚══════════════════════════════════════════════╝{RS}
""")

        while True:
            try:
                user_input = input(f"{CY}{BD}you › {RS}").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{DM}  Assistant closed.{RS}\n")
                break

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q", "back"]:
                print(f"\n{DM}  Back to main menu.{RS}\n")
                break

            print(f"{DM}  thinking...{RS}", end="\r")
            response = self.chat(user_input)

            # Clear the "thinking..." line
            print(" " * 20, end="\r")
            print(f"\n{MG}{BD}BR0THER › {RS}{response}\n")
            print(f"{DM}  [{self.llm_source}]{RS}\n")


if __name__ == "__main__":
    Assistant().run()
