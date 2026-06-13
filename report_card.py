#!/usr/bin/env python3
"""
report_card.py — READ-ONLY agent performance report.

This does NOT trade, change weights, or modify anything. It only READS your
existing database (data/agent.db) and shows which council agents have made
good calls, by joining the votes they cast (council_votes) against how those
tokens' trades actually turned out (positions).

This is the "measure your own output" half of self-improvement. It changes
zero behaviour — it just tells you the truth about who's been right.

Run it any time:   python3 report_card.py
"""

import sqlite3, os, sys

DB_PATH = "data/agent.db"

GR = "\033[92m"; RD = "\033[91m"; YL = "\033[93m"; CY = "\033[96m"; DM = "\033[2m"; BD = "\033[1m"; RS = "\033[0m"


def main():
    if not os.path.exists(DB_PATH):
        print(f"{YL}No database found at {DB_PATH} yet. Run the bot first so it can collect votes & trades.{RS}")
        return

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Make sure the tables we need actually exist (don't crash on a fresh DB)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "council_votes" not in tables:
        print(f"{YL}No council_votes table yet — no debates recorded so far.{RS}")
        return
    if "positions" not in tables:
        print(f"{YL}No positions table yet — no trades recorded so far.{RS}")
        return

    # Pull every closed position's outcome, keyed by token.
    # If the same token traded more than once, we take its average pnl_pct.
    outcomes = {}
    for row in db.execute(
        "SELECT token, AVG(pnl_pct) AS avg_pnl, COUNT(*) AS n "
        "FROM positions WHERE status='CLOSED' GROUP BY token"
    ):
        outcomes[row["token"]] = {"pnl": row["avg_pnl"] or 0.0, "n": row["n"]}

    if not outcomes:
        print(f"{CY}{BD}Agent Report Card{RS}\n")
        print(f"{YL}No closed trades yet, so there are no outcomes to grade votes against.{RS}")
        print(f"{DM}Let the bot run (paper mode is fine) until some positions close, then run this again.{RS}")
        db.close()
        return

    # For each agent, look at the tokens they voted TRADE on that later closed,
    # and see how those trades did.
    agents = {}
    for row in db.execute("SELECT token, agent, decision, confidence FROM council_votes"):
        token = row["token"]
        if token not in outcomes:
            continue  # no closed trade for this token yet — can't grade it
        agent = row["agent"] or "unknown"
        a = agents.setdefault(agent, {"trade_calls": 0, "trade_wins": 0, "pnl_sum": 0.0, "votes": 0})
        a["votes"] += 1
        if (row["decision"] or "").upper() == "TRADE":
            a["trade_calls"] += 1
            pnl = outcomes[token]["pnl"]
            a["pnl_sum"] += pnl
            if pnl > 0:
                a["trade_wins"] += 1

    db.close()

    if not agents:
        print(f"{CY}{BD}Agent Report Card{RS}\n")
        print(f"{YL}Votes exist, but none of them are on tokens that have closed trades yet.{RS}")
        print(f"{DM}Give it more time — once voted tokens close, they'll show up here.{RS}")
        return

    # Print the report, sorted by win rate (only meaningful for agents with trade calls)
    print(f"\n{CY}{BD}╔══════════════════════════════════════════════════════════╗{RS}")
    print(f"{CY}{BD}║                  AGENT REPORT CARD                       ║{RS}")
    print(f"{CY}{BD}╚══════════════════════════════════════════════════════════╝{RS}")
    print(f"{DM}Read-only. Joins each agent's TRADE votes to how those tokens' trades closed.{RS}\n")

    ranked = sorted(
        agents.items(),
        key=lambda kv: (kv[1]["trade_wins"] / kv[1]["trade_calls"]) if kv[1]["trade_calls"] else -1,
        reverse=True
    )

    print(f"  {'AGENT':<14}{'TRADE CALLS':>12}{'WIN RATE':>11}{'AVG PnL':>11}")
    print(f"  {'-'*14}{'-'*12:>12}{'-'*11:>11}{'-'*11:>11}")
    for agent, a in ranked:
        calls = a["trade_calls"]
        if calls == 0:
            print(f"  {agent:<14}{calls:>12}{'—':>11}{'—':>11}   {DM}(no TRADE calls graded yet){RS}")
            continue
        wr = a["trade_wins"] / calls * 100
        avg = a["pnl_sum"] / calls
        wr_col = GR if wr >= 50 else (YL if wr >= 35 else RD)
        avg_col = GR if avg > 0 else RD
        print(f"  {agent:<14}{calls:>12}{wr_col}{wr:>10.0f}%{RS}{avg_col}{avg:>10.1f}%{RS}")

    # Honest sample-size warning — this is the important part.
    total_graded = sum(a["trade_calls"] for a in agents.values())
    print()
    if total_graded < 50:
        print(f"{YL}{BD}⚠ Small sample ({total_graded} graded calls).{RS}")
        print(f"{YL}  These numbers are mostly NOISE until you have a few hundred graded calls.{RS}")
        print(f"{YL}  Do NOT change agent weights based on this yet — a hot streak isn't skill.{RS}")
    else:
        print(f"{DM}{total_graded} graded calls. Patterns are starting to mean something — but markets")
        print(f"  are noisy, so treat this as a hint, not gospel. Bigger sample = more trustworthy.{RS}")
    print()


if __name__ == "__main__":
    main()
