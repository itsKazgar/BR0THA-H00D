import subprocess, sys, os, time
C = '\033[96m\033[1m'
G = '\033[92m'
Y = '\033[93m'
X = '\033[0m'
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

print(C+"""
██████╗ ██████╗  ██████╗ ████████╗██╗  ██╗███████╗██████╗       ██╗  ██╗ ██████╗  ██████╗ ██████╗ 
██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗      ██║  ██║██╔═████╗██╔═████╗██╔══██╗
██████╔╝██████╔╝██║   ██║   ██║   ███████║█████╗  ██████╔╝█████╗███████║██║██╔██║██║██╔██║██║  ██║
██╔══██╗██╔══██╗██║   ██║   ██║   ██╔══██║██╔══╝  ██╔══██╗╚════╝██╔══██║████╔╝██║████╔╝██║██║  ██║
██████╔╝██║  ██║╚██████╔╝   ██║   ██║  ██║███████╗██║  ██║      ██║  ██║╚██████╔╝╚██████╔╝██████╔╝ 
╚═════╝ ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝      ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═════╝ 
"""+X)

from core import brain
brain.init_db()
brain.brain_summary()

# ── Mode selector ─────────────────────────────────────────
has_ai = any(os.getenv(k) for k in ["OPENROUTER_API_KEY","GROQ_API_KEY","ANTHROPIC_API_KEY","OPENAI_API_KEY"])

ai_status = f"{G}✅ AI ready{X}" if has_ai else f"{Y}⚠  no key — uses rules+{X}"
print(f"""
SELECT MODE




  {G}1{X}  Paper trade    rule-based only, zero config
  {G}2{X}  Full AI        all 7 agents ({ai_status})
  {G}3{X}  Custom         manage agents via dashboard
  {G}4{X}  Quick start    all agents, no questions
  {G}s{X}  Setup keys     python3 setup.py
""")

try:
    choice = input(f"  {G}Select (1-4, or Enter for quick start):{X} ").strip() or "4"
except (KeyboardInterrupt, EOFError):
    choice = "4"

AGENTS_CORE    = ["agents/trading/scanner.py", "agents/trading/trader.py"]
AGENTS_SUPPORT = ["agents/trading/whale_tracker.py", "agents/trading/news_scout.py",
                  "agents/trading/pump_hunter.py", "agents/trading/risk_manager.py",
                  "agents/trading/memory_keeper.py"]

if choice == "1":
    print(f"\n  {G}📄 Paper mode — rule-based trading{X}")
    os.environ["OPENROUTER_API_KEY"] = ""
    os.environ["GROQ_API_KEY"] = ""
    selected = AGENTS_CORE + ["agents/trading/risk_manager.py", "agents/trading/memory_keeper.py"]
elif choice == "2":
    print(f"\n  {G}🤖 Full AI mode — all 7 agents{X}")
    if not has_ai:
        print(f"  {Y}⚠ No AI key found — run python3 setup.py to add one{X}")
    selected = AGENTS_CORE + AGENTS_SUPPORT
elif choice == "3":
    print(f"\n  {C}⚙️  Custom mode — choose agents:{X}\n")
    selected = list(AGENTS_CORE)
    names = {
        "agents/trading/whale_tracker.py": "🐋 Whale Tracker  — smart wallet watcher",
        "agents/trading/news_scout.py":    "📰 News Scout      — market sentiment",
        "agents/trading/pump_hunter.py":   "💊 Pump Hunter     — early pump.fun gems",
        "agents/trading/risk_manager.py":  "🛡️  Risk Manager   — portfolio safety",
        "agents/trading/memory_keeper.py": "🧠 Memory Keeper   — learns from trades",
    }
    for path, label in names.items():
        try:
            ans = input(f"  Enable {label}? (Y/n): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            ans = "y"
        if ans != "n":
            selected.append(path)
else:
    print(f"\n  {G}🚀 Quick start — all agents{X}")
    selected = AGENTS_CORE + AGENTS_SUPPORT

print()
print("Starting agents...\n")

PYTHON = sys.executable   # uses whatever python is running start.py — no more 'python not found'

procs = []
# ── Agent roster ─────────────────────────────────────────
# Comment out any agent you don't want to run
# Scanner and Trader are required — the rest are optional
ALL_AGENTS = [
    [PYTHON, "agents/trading/scanner.py"],       # required — finds signals
    [PYTHON, "agents/trading/trader.py"],         # required — executes trades
    [PYTHON, "agents/trading/whale_tracker.py"],  # optional — watches smart wallets
    [PYTHON, "agents/trading/news_scout.py"],     # optional — crypto news sentiment
    [PYTHON, "agents/trading/pump_hunter.py"],    # optional — early pump.fun gems
    [PYTHON, "agents/trading/risk_manager.py"],   # optional — portfolio safety
    [PYTHON, "agents/trading/memory_keeper.py"],  # optional — learns from trades
]

root = os.path.dirname(os.path.abspath(__file__))

# Only start agents whose files actually exist
agents = [[PYTHON, a] for a in selected if os.path.exists(os.path.join(root, a))]

for cmd in agents:
    p = subprocess.Popen(cmd, cwd=root)
    procs.append(p)
    print(f"  {G}✅{X} started {cmd[1]} (pid {p.pid})")
    time.sleep(2)   # give scanner time to write first signals before trader reads

print("\n🚀 All agents running. Press Ctrl+C to stop all.\n")

try:
    while True:
        time.sleep(5)
        for i, p in enumerate(procs):
            if p.poll() is not None:
                name = agents[i][1]
                print(f"  ⚠️  {name} crashed (exit {p.returncode}) — restarting in 5s...")
                time.sleep(5)
                procs[i] = subprocess.Popen(agents[i], cwd=root)
                print(f"  ✅ restarted {name} (pid {procs[i].pid})")
except KeyboardInterrupt:
    print("\nShutting down all agents...")
    for p in procs:
        p.terminate()
    print("Done.")
