import subprocess, sys, os, time
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

print("""
██████╗ ██████╗  ██████╗ ████████╗██╗  ██╗███████╗██████╗
██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗
██████╔╝██████╔╝██║   ██║   ██║   ███████║█████╗  ██████╔╝
██╔══██╗██╔══██╗██║   ██║   ██║   ██╔══██║██╔══╝  ██╔══██╗
██████╔╝██║  ██║╚██████╔╝   ██║   ██║  ██║███████╗██║  ██║
╚═════╝ ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
       H00D — Solana Alpha Collective  [7 AGENTS]
""")

from core import brain
brain.init_db()
brain.brain_summary()

PYTHON = sys.executable
ROOT   = os.path.dirname(os.path.abspath(__file__))

AGENTS = [
    ("agents/trading/scanner.py",      0,   "📡 Scanner      — hunts trending tokens across all sources"),
    ("agents/intel/whale_tracker.py",  2,   "🐋 Whale Tracker — watches smart wallet moves"),
    ("agents/intel/news_scout.py",     4,   "📰 News Scout    — scans crypto news & sentiment"),
    ("agents/intel/pump_hunter.py",    6,   "💊 Pump Hunter   — finds early pump.fun gems"),
    ("agents/intel/risk_manager.py",   8,   "⚠️  Risk Manager  — monitors portfolio & enforces limits"),
    ("agents/intel/analyst.py",        10,  "🧠 Analyst       — AI reasoning on every signal"),
    ("agents/trading/trader.py",       14,  "💸 Trader        — executes paper trades"),
    ("agents/intel/memory_keeper.py",  18,  "📚 Memory Keeper — logs learnings every 5 min"),
]

print("Deploying the crew...\n")

procs = []
for script, delay, desc in AGENTS:
    if delay > 0:
        time.sleep(delay)
    p = subprocess.Popen([PYTHON, script], cwd=ROOT)
    procs.append((p, script))
    print(f"  ✅ {desc}  (pid {p.pid})")

print(f"""
╔══════════════════════════════════════════════╗
║   🚀 BR0THER-H00D COLLECTIVE IS LIVE        ║
║   {len(AGENTS)} agents running | Paper mode            ║
║   Press Ctrl+C to shut down all agents      ║
╚══════════════════════════════════════════════╝
""")

try:
    while True:
        time.sleep(5)
        for i, (p, script) in enumerate(procs):
            if p.poll() is not None:
                print(f"\n  ⚠️  {script} crashed (exit {p.returncode}) — restarting...")
                time.sleep(3)
                new_p = subprocess.Popen([PYTHON, script], cwd=ROOT)
                procs[i] = (new_p, script)
                print(f"  ✅ Restarted {script} (pid {new_p.pid})")
except KeyboardInterrupt:
    print("\n🛑 Shutting down the collective...")
    for p, script in procs:
        p.terminate()
        print(f"  stopped {script}")
    print("Done. See you next run.")
