"""
ASSISTANT LAUNCHER — sub-menu to pick which assistant to run
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, llm

CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'
BD='\033[1m';  DM='\033[2m';  RS='\033[0m';  MG='\033[95m'

ASSISTANTS = [
    {"id":"trader",   "name":"Trader Assistant",   "emoji":"📈", "color":GR,
     "description":"Portfolio, PnL, alerts",
     "brothers":["crypto","portfolio","alerts","telegram","tasks"],
     "system":"You are a crypto trading assistant. Help with portfolio, trades, and market data."},
    {"id":"research", "name":"Research Assistant",  "emoji":"🔍", "color":CY,
     "description":"Search, read URLs, summarize",
     "brothers":["search","scraper","tasks"],
     "system":"You are a research assistant. Find information, summarize articles, answer questions."},
    {"id":"personal", "name":"Personal Assistant",  "emoji":"🗓️", "color":YL,
     "description":"Todos, notes, habits, journal",
     "brothers":["tasks","telegram"],
     "system":"You are a personal productivity assistant. Help stay organized and track habits."},
    {"id":"business", "name":"Business Assistant",  "emoji":"💼", "color":MG,
     "description":"Emails, invoices, content",
     "brothers":["search","scraper","tasks","telegram"],
     "system":"You are a business assistant. Help with emails, content, and business tasks."},
    {"id":"orchestrator", "name":"Orchestrator",      "emoji":"🧠", "color":MG,
     "description":"Tell it anything, it delegates automatically",
     "brothers":[],
     "system":"You are the orchestrator. Delegate tasks to the right brothers and combine results."},
    {"id":"full",     "name":"Full Team",            "emoji":"👥", "color":RD,
     "description":"All brothers, full power",
     "brothers":[],
     "system":"You are BR0THER, a powerful AI assistant with all tools available."},
]

def launch(cfg):
    from agents.assistant import Assistant
    brothers_filter = cfg["brothers"]

    class SpecializedAssistant(Assistant):
        def __init__(self):
            super().__init__()
            self.name            = cfg["name"]
            self.emoji           = cfg["emoji"]
            self.color           = cfg["color"]
            self.sys_prompt      = cfg["system"]
            self.brothers_filter = brothers_filter

        def chat(self, user_input):
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
                from brothers import _brothers
                for key, mod in _brothers.items():
                    if self.brothers_filter and key not in self.brothers_filter:
                        continue
                    if not getattr(mod, "ENABLED", True):
                        continue
                    try:
                        result = mod.run(user_input)
                        if result is not None:
                            self.llm_source = mod.NAME
                            return result
                    except:
                        pass
            except:
                pass
            self.conversation.append({"role": "user", "content": user_input})
            if len(self.conversation) > 40:
                self.conversation = self.conversation[-40:]
            history = ""
            for turn in self.conversation[:-1]:
                role = "Assistant" if turn["role"] == "assistant" else "User"
                history += f"{role}: {turn['content']}\n"
            prompt   = f"{history}User: {user_input}\nAssistant:"
            response, source = llm.think(prompt, system=self.sys_prompt)
            self.llm_source  = source
            if not response:
                response = "Could not process that. Try again."
            self.conversation.append({"role": "assistant", "content": response})
            return response

        def run(self):
            import requests
            os.system("clear")
            sol_price = None
            try:
                r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=6)
                sol_price = float(r.json()["solana"]["usd"])
            except:
                pass
            from brothers import list_all
            all_bros = list_all()
            active   = [b for b in all_bros if not self.brothers_filter or b["id"] in self.brothers_filter]
            bros_str = ", ".join(b["name"].replace(" Brother","") for b in active)
            print(f"""
{self.color}{BD}╔══════════════════════════════════════════════╗
║  {self.emoji}  {self.name:<40}║
╠══════════════════════════════════════════════╣{RS}
  {DM}🧠 AI      {RS}  {llm.status()}
  {DM}👥 Team    {RS}  {bros_str}
  {DM}◎  SOL     {RS}  {'$' + f'{sol_price:,.2f}' if sol_price else 'unknown'}
{self.color}{BD}╠══════════════════════════════════════════════╣{RS}
  Type help for commands or just ask anything.
  Type exit to go back.
{self.color}{BD}╚══════════════════════════════════════════════╝{RS}
""")
            while True:
                try:
                    user_input = input(f"{self.color}{BD}you › {RS}").strip()
                except (EOFError, KeyboardInterrupt):
                    print(f"\n{DM}  Closed.{RS}\n")
                    break
                if not user_input:
                    continue
                if user_input.lower() in ["exit","quit","q","back"]:
                    print(f"\n{DM}  Back to assistant menu.{RS}\n")
                    break
                print(f"{DM}  thinking...{RS}", end="\r")
                response = self.chat(user_input)
                print(" " * 20, end="\r")
                print(f"\n{self.color}{BD}BR0THER › {RS}{response}\n")
                print(f"{DM}  [{self.llm_source}]{RS}\n")

    SpecializedAssistant().run()

def run():
    W = 60
    while True:
        os.system("clear")
        ROWS = []
        for i, a in enumerate(ASSISTANTS, 1):
            ROWS.append(f"[{i}] {a['name']:<22}  {a['description']}")
        ROWS.append("[0]  Back")
        W2 = max(len(r) for r in ROWS) + 4
        title = "🤖  BR0THER ASSISTANT TEAM"
        tpad  = W2 - len(title) - 3
        print(f"\n{CY}{BD}  ╔{'═'*W2}╗")
        print(f"{CY}{BD}  ║  {title}{' '*tpad}  ║")
        print(f"{CY}{BD}  ╠{'═'*W2}╣{RS}")
        for i, a in enumerate(ASSISTANTS, 1):
            line = ROWS[i-1]
            pad  = W2 - len(line) - 2
            print(f"{CY}{BD}  ║ {a['color']}{line}{RS}{' '*pad} {CY}{BD}║{RS}")
        bpad = W2 - len("[0]  Back") - 2
        print(f"{CY}{BD}  ║ {DM}[0]  Back{RS}{' '*bpad} {CY}{BD}║{RS}")
        print(f"{CY}{BD}  ╚{'═'*W2}╝{RS}\n")
        try:
            choice = input(f"{CY}  Select (0-{len(ASSISTANTS)}): {RS}").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if choice == "0" or choice.lower() in ["exit","back"]:
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ASSISTANTS):
                launch(ASSISTANTS[idx])
        except ValueError:
            pass

if __name__ == "__main__":
    run()
