"""
BRAIN — Shared memory layer for BR0THER-H00D collective.
SQLite-backed. All agents read/write through here.
"""
import sqlite3, json, os, time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "brain.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT    NOT NULL,
                agent     TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                type      TEXT    DEFAULT 'general',
                tags      TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS learnings (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT    NOT NULL,
                agent     TEXT    NOT NULL,
                topic     TEXT    NOT NULL,
                insight   TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS state (
                agent     TEXT    PRIMARY KEY,
                data      TEXT    NOT NULL,
                updated   TEXT    NOT NULL
            );
        """)

def remember(agent: str, content: str, type: str = "general", tags: str = ""):
    with _conn() as c:
        c.execute(
            "INSERT INTO memories (ts, agent, content, type, tags) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), agent, content, type, tags)
        )

def recall(agent: str = None, type: str = None, limit: int = 20) -> list:
    query  = "SELECT * FROM memories WHERE 1=1"
    params = []
    if agent:
        query += " AND agent = ?"; params.append(agent)
    if type:
        query  += " AND type = ?";  params.append(type)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _conn() as c:
        rows = c.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def learn(agent: str, topic: str, insight: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO learnings (ts, agent, topic, insight) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), agent, topic, insight)
        )

def get_learnings(topic: str = None, limit: int = 10) -> list:
    query  = "SELECT * FROM learnings WHERE 1=1"
    params = []
    if topic:
        query += " AND topic LIKE ?"; params.append(f"%{topic}%")
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _conn() as c:
        rows = c.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def load_state(agent: str) -> dict:
    with _conn() as c:
        row = c.execute("SELECT data FROM state WHERE agent=?", (agent,)).fetchone()
    return json.loads(row["data"]) if row else {}

def save_state(agent: str, data: dict):
    with _conn() as c:
        c.execute(
            "INSERT INTO state (agent, data, updated) VALUES (?,?,?) "
            "ON CONFLICT(agent) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (agent, json.dumps(data), datetime.now().isoformat())
        )

def brain_summary():
    with _conn() as c:
        mem_count = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        lea_count = c.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
    print(f"  🧠 Brain: {mem_count} memories | {lea_count} learnings | db={DB_PATH}\n")

def share_idea(agent: str, content: str, type: str = "idea", tags: str = "", **kwargs):
    """Alias used by scanner — stores a signal/idea to shared memory."""
    remember(agent, content, type=type, tags=tags)
