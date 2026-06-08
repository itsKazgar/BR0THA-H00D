"""
ORCHESTRATOR BROTHER — The Boss
Understands any task, delegates to the right brothers, combines results.
"""
import os, sys, requests, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, llm
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Orchestrator"
DESCRIPTION = "Boss brother — delegates any task to the right brothers automatically"
ENABLED     = True
COMMANDS    = ["do <anything>", "boss <task>", "run <task>"]

TRIGGERS = ["what should", "what do i", "should i", "tell me about","do ", "boss ", "run ", "orchestrate ", "handle ",
            "can you ", "please ", "i need ", "help me "]

def _get_brothers_info():
    """Get all available brothers and what they can do."""
    from brothers import list_all
    bros = list_all()
    lines = []
    for b in bros:
        if b["id"] == "orchestrator":
            continue
        cmds = ", ".join(b["commands"][:3]) if b["commands"] else "general tasks"
        lines.append(f'- {b["id"]}: {b["name"]} — {b["description"]} | commands: {cmds}')
    return "\n".join(lines)

def _ask_orchestrator(task: str, brothers_info: str) -> list:
    """Ask the LLM which brothers to use and what commands to run."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return []

    prompt = f"""You are an orchestrator AI. A user gave you this task:
"{task}"

You have these brothers (tools) available:
{brothers_info}

Your job: break the task into steps and assign each step to the right brother.
Respond ONLY with a JSON array like this:
[
  {{"brother": "crypto", "command": "price SOL", "reason": "get current SOL price"}},
  {{"brother": "search", "command": "search solana news today", "reason": "find latest news"}},
  {{"brother": "tasks", "command": "todo follow up on SOL", "reason": "save reminder"}}
]

Rules:
- Only use brothers from the list above
- Each command must match what that brother can actually do
- Maximum 4 steps
- If a brother can't do something, skip it
- Return ONLY the JSON array, nothing else"""

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile", "max_tokens": 500,
                  "temperature": 0.1,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=15)
        if r.status_code != 200:
            return []
        text = r.json()["choices"][0]["message"]["content"].strip()
        # Extract JSON array
        start = text.find("[")
        end   = text.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        return json.loads(text[start:end])
    except Exception as e:
        print(f"  [orchestrator] plan failed: {e}")
        return []

def _summarize_results(task: str, results: list) -> str:
    """Ask LLM to combine all results into one coherent response."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key or not results:
        return "\n\n".join(r["output"] for r in results if r.get("output"))

    results_text = ""
    for r in results:
        results_text += f"\n[{r['brother']}]: {r['output'][:400]}\n"

    prompt = f"""The user asked: "{task}"

Here are the results from each tool:
{results_text}

Write a clear, helpful summary that answers the user's request using all the above information.
Be concise and direct. Use bullet points if helpful."""

    try:
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile", "max_tokens": 600,
                  "temperature": 0.3,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=15)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except:
        pass
    return "\n\n".join(r["output"] for r in results if r.get("output"))

def run(user_input: str):
    lower = user_input.lower().strip()

    # Only trigger on explicit orchestrator commands or multi-part tasks
    is_trigger    = any(lower.startswith(t) for t in TRIGGERS)
    is_multi_task = " and " in lower and len(lower) > 30
    is_complex    = len(lower.split()) >= 7

    if not (is_trigger or is_multi_task or is_complex):
        return None

    # Don't intercept simple commands other brothers handle
    simple = ["price ", "sol", "fear", "greed", "todo ", "note ",
              "search ", "scrape ", "portfolio", "stats", "gm", "briefing"]
    if any(lower.startswith(s) for s in simple):
        return None

    print(f"\n  🧠 Orchestrator analyzing task...")

    brothers_info = _get_brothers_info()
    plan          = _ask_orchestrator(user_input, brothers_info)

    if not plan:
        return None  # fall through to regular LLM

    print(f"  📋 Plan: {len(plan)} steps")

    # Execute each step
    from brothers import _brothers
    results = []
    for i, step in enumerate(plan, 1):
        brother_id = step.get("brother", "")
        command    = step.get("command", "")
        reason     = step.get("reason", "")

        if not brother_id or not command:
            continue

        mod = _brothers.get(brother_id)
        if not mod:
            continue

        print(f"  [{i}/{len(plan)}] {mod.NAME} → {command}")
        try:
            output = mod.run(command)
            if output:
                results.append({
                    "brother": mod.NAME,
                    "command": command,
                    "reason":  reason,
                    "output":  output,
                })
                # Save to brain
                brain.remember("orchestrator",
                    f"TASK: {user_input[:60]} | STEP: {command} | RESULT: {output[:80]}",
                    type="orchestration", tags="orchestrator,task")
        except Exception as e:
            print(f"  [orchestrator] {brother_id} failed: {e}")

    if not results:
        return None

    # Combine results
    print(f"  ✅ Combining {len(results)} results...")
    summary = _summarize_results(user_input, results)

    # Show which brothers contributed
    contributors = " + ".join(r["brother"] for r in results)
    return f"{summary}\n\n{chr(8212)*40}\n🤝 Team: {contributors}"

