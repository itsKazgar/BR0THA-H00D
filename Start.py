import subprocess, sys, os, signal, time
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

CY = "\033[96m";  GR = "\033[92m";  YL = "\033[93m"
RD = "\033[91m";  DM = "\033[2m";   RS = "\033[0m"
BD = "\033[1m";   MG = "\033[95m"

PYTHON = sys.executable
ROOT   = os.path.dirname(os.path.abspath(__file__))

AGENTS = [
    ("agents/trading/scanner.py",     "Scanner       — hunts trending tokens"),
    ("agents/intel/whale_tracker.py", "Whale Tracker — watches smart wallet moves"),
    ("agents/intel/news_scout.py",    "News Scout    — scans crypto news & sentiment"),
    ("agents/intel/pump_hunter.py",   "Pump Hunter   — finds early pump.fun gems"),
    ("agents/intel/risk_manager.py",  "Risk Manager  — monitors portfolio & limits"),
    ("agents/intel/analyst.py",       "Analyst       — AI reasoning on every signal"),
    ("agents/trading/trader.py",      "Trader        — executes trades"),
    ("agents/intel/memory_keeper.py", "Memory Keeper — logs learnings every 5 min"),
]

procs = []

def shutdown(sig=None, frame=None):
    if procs:
        print(CY + "\n  Shutting down all agents..." + RS)
        for p, script in procs:
            try:    p.terminate(); p.wait(timeout=3)
            except:
                try: p.kill()
                except: pass
        print(GR + "  All agents stopped. See you next run.\n" + RS)
    else:
        print(RS + "\n  Exited.\n")
    sys.exit(0)

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)
try:
    kill_orphans()
except Exception:
    pass

def box(text="", color="", width=55):
    pad = width - len(text)
    return CY + "  ║ " + color + text + RS + " " * pad + CY + "║" + RS

W = 55

os.system("clear")

print(CY + BD + r"""
██████╗ ██████╗  ██████╗ ████████╗██╗  ██╗███████╗██████╗ ██╗  ██╗ ██████╗  ██████╗ ██████╗
██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗██║  ██║██╔═══██╗██╔═══██╗██╔══██╗
██████╔╝██████╔╝██║   ██║   ██║   ███████║█████╗  ██████╔╝███████║██║   ██║██║   ██║██║  ██║
██╔══██╗██╔══██╗██║   ██║   ██║   ██╔══██║██╔══╝  ██╔══██╗██╔══██║██║   ██║██║   ██║██║  ██║
██████╔╝██║  ██║╚██████╔╝   ██║   ██║  ██║███████╗██║  ██║██║  ██║╚██████╔╝╚██████╔╝██████╔╝
╚═════╝ ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═════╝
""" + RS)

print(CY + "        Solana Alpha Collective  —  8 Agents" + RS)
print()


from core import brain
brain.init_db()
brain.brain_summary()
print()

print(CY + "  ╔" + "═" * W + "╗")
print(box())
print(box("SELECT MODE", BD + CY))
print(box())
print(CY + "  ╠" + "═" * W + "╣")
print(box())
print(box("[1]  Solo Paper Trade  — auto trader, no agents", GR))
print(box("[2]  Paper + Agents    — auto trader + 8 agents ",  CY))
print(box("[3]  Live Trading      — real funds, all agents active",   MG))
print(box("[4]  Custom Trading Mode — build & edit your own agents",    YL))
print(box("[5]  Assistant Mode   — personal AI assistant & tasks",   RD))
print(box("[0]  Exit",                                                DM))
print(box())
print(CY + "  ╚" + "═" * W + "╝" + RS)
print()

try:
    choice = input(CY + "  Select (0-5): " + RS).strip()
except (EOFError, KeyboardInterrupt):
    shutdown()
print()

if choice == "0":
    print(DM + "  Exited.\n" + RS); sys.exit(0)

elif choice == "1":
    # ── Solo Paper Trade — trader runs alone, no agent signals ──────────────────────────
    os.environ["TRADE_MODE"] = "paper"
    solo = [("agents/trading/trader.py", "Trader  — running solo, no agent signals")]
    runnable = [(p, d) for p, d in solo if os.path.exists(os.path.join(ROOT, p))]
    if not runnable:
        print(RD + "  agents/trading/trader.py not found.\n" + RS); sys.exit(1)
    print(GR + BD + "  SOLO PAPER TRADE — trader only, no agent signals\n" + RS)
    print(DM + "  ─────────────────────────────────────────────────────────" + RS)
    for script, desc in runnable:
        p = subprocess.Popen([PYTHON, script], cwd=ROOT)
        procs.append((p, script))
        print(CY + f"  + {desc}" + DM + f"  (pid {p.pid})" + RS)
    print()
    print(CY + BD + "  ╔" + "═" * W + "╗")
    print(CY + BD + "  ║ " + RS + GR + BD + "SOLO TRADER IS LIVE  · paper mode" + RS + " " * 20 + CY + BD + "║" + RS)
    print(CY + BD + box("Ctrl+C to shut down", DM))
    print(CY + BD + "  ╚" + "═" * W + "╝" + RS)
    print()
    while True:
        time.sleep(5)
        for i, (p, script) in enumerate(procs):
            if p.poll() is not None:
                print(RD + f"  ! {script} crashed — restarting..." + RS)
                time.sleep(2)
                new_p = subprocess.Popen([PYTHON, script], cwd=ROOT)
                procs[i] = (new_p, script)
                print(GR + f"  + Restarted (pid {new_p.pid})" + RS)

elif choice == "2":
    label  = "Paper + Agents"
    active = AGENTS
    os.environ["TRADE_MODE"] = "paper"

elif choice == "3":
    print(RD + BD + "  ⚠  LIVE MODE — real money will be traded!" + RS)
    print()
    wallet = os.environ.get("WALLET_ADDRESS", "")
    if not wallet:
        print(RD + "  No WALLET_ADDRESS in .env — add it first.\n" + RS); sys.exit(1)
    print(DM + f"  Wallet: {wallet[:6]}...{wallet[-4:]}" + RS)
    print()
    try:    confirm = input(YL + "  Type YES to confirm live trading: " + RS).strip()
    except: shutdown()
    if confirm != "YES":
        print(DM + "\n  Cancelled.\n" + RS); sys.exit(0)
    label  = "LIVE"
    active = AGENTS
    os.environ["TRADE_MODE"] = "live"
    print()

elif choice == "4":
    # ── Custom Mode — launch dashboard ────────────────────────────────────
    os.environ["TRADE_MODE"] = "paper"
    print(YL + BD + "  CUSTOM MODE — launching dashboard\n" + RS)
    print(DM + "  Starting API server + dashboard..." + RS)
    print()
    api_proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "brotha_api:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=ROOT
    )
    time.sleep(2)
    print(GR + "  ✅ Dashboard running at: " + BD + "http://localhost:8000" + RS)
    print(DM + "  • Add / edit / delete agents from the browser" + RS)
    print(DM + "  • Ctrl+C here to shut down the dashboard" + RS)
    print()
    try:
        api_proc.wait()
    except KeyboardInterrupt:
        api_proc.terminate()
        print(CY + "\n  Dashboard stopped.\n" + RS)
    sys.exit(0)

elif choice == "5":
    print(MG + BD + "  ASSISTANT MODE — your personal AI\n" + RS)
    import agents.assistant_launcher as launcher
    launcher.run()
    sys.exit(0)

else:
    print(DM + "  Unknown option — exited.\n" + RS); sys.exit(0)

# ── modes 2 & 3 — launch agents ───────────────────────────────────────────
runnable = [(p, d) for p, d in active if os.path.exists(os.path.join(ROOT, p))]
skipped  = [(p, d) for p, d in active if not os.path.exists(os.path.join(ROOT, p))]

if skipped:
    print(YL + f"  ⚠  Skipping {len(skipped)} missing scripts:" + RS)
    for p, d in skipped:
        print(DM + f"       {p}" + RS)
    print()

if not runnable:
    print(RD + "  No runnable agents found.\n" + RS); sys.exit(1)

clr = RD if label == "LIVE" else GR
print(clr + f"  {label} — launching {len(runnable)} agents...\n" + RS)
print(DM + "  ─────────────────────────────────────────────────────────" + RS)

for i, (script, desc) in enumerate(runnable):
    if i > 0: time.sleep(1.5)
    p = subprocess.Popen([PYTHON, script], cwd=ROOT)
    procs.append((p, script))
    print(CY + f"  + {desc}" + DM + f"  (pid {p.pid})" + RS)

n = len(procs)
print()
print(CY + BD + "  ╔" + "═" * W + "╗")
live_text = f"BR0THER-H00D IS LIVE  ·  {n} agents"
print(CY + BD + "  ║ " + RS + GR + BD + live_text + RS + " " * (W - len(live_text) - 1) + CY + BD + "║" + RS)
print(CY + BD + box("Ctrl+C to shut down all agents cleanly", DM))
print(CY + BD + "  ╚" + "═" * W + "╝" + RS)
print()

while True:
    time.sleep(5)
    for i, (p, script) in enumerate(procs):
        if p.poll() is not None:
            print(RD + f"  ! {script} crashed (exit {p.returncode}) — restarting..." + RS)
            time.sleep(2)
            new_p = subprocess.Popen([PYTHON, script], cwd=ROOT)
            procs[i] = (new_p, script)
            print(GR + f"  + Restarted {script} (pid {new_p.pid})" + RS)
