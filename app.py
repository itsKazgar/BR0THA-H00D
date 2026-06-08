#!/usr/bin/env python3
import os, sqlite3
from datetime import datetime
from flask import Flask, render_template_string, jsonify
app = Flask(__name__)
BRAIN_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "brain.db")
def get_latest_brief():
    if os.path.exists(BRAIN_DB):
        try:
            c = sqlite3.connect(BRAIN_DB); c.row_factory = sqlite3.Row
            row = c.execute("SELECT content, ts FROM memories WHERE agent IN ('orchestrator','briefing','newsletter','content') ORDER BY id DESC LIMIT 1").fetchone()
            c.close()
            if row: return row["content"], row["ts"][:16].replace("T"," ")
        except Exception: pass
    return ("Run scheduled_council.py to generate a brief, then refresh."), datetime.now().strftime("%Y-%m-%d %H:%M")
@app.route("/")
def home():
    brief, ts = get_latest_brief()
    return render_template_string(PAGE, brief=brief, brief_ts=ts)
PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BR0THER-H00D</title>
<style>body{background:#0d0e12;color:#e8e6e0;font-family:monospace;line-height:1.6;max-width:760px;margin:0 auto;padding:64px 24px}
h1{color:#d4a857;font-size:38px}.card{background:#15171e;border:1px solid #262932;border-radius:14px;padding:30px;margin:24px 0}
.brief{white-space:pre-wrap}.ts{color:#8b8d98;font-size:12px;margin-top:18px}</style></head>
<body><h1>Daily Brief</h1><div class="card"><div class="brief">{{ brief }}</div><div class="ts">Updated {{ brief_ts }}</div></div></body></html>"""
if __name__ == "__main__":
    print("dashboard on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
