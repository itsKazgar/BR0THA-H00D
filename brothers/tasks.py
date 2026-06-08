import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain

NAME        = "Tasks Brother"
DESCRIPTION = "Todos, notes, reminders — saved to brain memory"
ENABLED     = True
COMMANDS    = ["todo <task>", "note <text>", "remember <text>", "todos", "notes"]

def run(user_input):
    lower = user_input.lower().strip()
    if lower.startswith("todo ") or lower.startswith("task "):
        task = user_input.split(" ", 1)[1].strip()
        brain.remember("assistant", f"TODO: {task}", type="todo", tags="todo")
        return f"✅ Task saved: {task}"
    if lower in ["todos", "tasks", "my tasks"]:
        todos = brain.recall(type="todo", limit=20)
        if not todos:
            return "No tasks yet. Try: todo buy groceries"
        lines = [f"  • {t['content'].replace('TODO: ','')} [{t.get('ts','')[:10]}]" for t in todos]
        return "📋 Your tasks:\n" + "\n".join(lines)
    if lower.startswith("note ") or lower.startswith("remember "):
        note = user_input.split(" ", 1)[1].strip()
        brain.remember("assistant", note, type="note", tags="note")
        return f"✅ Saved: {note}"
    if lower in ["notes", "memory", "recall"]:
        mems = brain.recall(limit=10)
        if not mems:
            return "Nothing saved yet."
        lines = [f"  • {m['content'][:80]} [{m.get('ts','')[:10]}]" for m in mems[:8]]
        return "🧠 Memory:\n" + "\n".join(lines)
    return None
