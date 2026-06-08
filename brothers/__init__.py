import os, importlib.util, traceback

_brothers = {}

# Brothers tried in this order. Orchestrator last so it only
# catches what no specific brother claimed. Anything not listed
# falls in the middle, alphabetically.
PRIORITY = ["council", "briefing", "crypto", "stocks", "portfolio",
            "alerts", "tasks", "search", "alpha", "hn", "reddit",
            "scraper", "weather", "burner", "telegram", "orchestrator"]

def load_all():
    folder = os.path.dirname(__file__)
    for fname in sorted(os.listdir(folder)):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        name = fname[:-3]
        try:
            spec   = importlib.util.spec_from_file_location(name, os.path.join(folder, fname))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "NAME") and hasattr(module, "run"):
                _brothers[name] = module
        except Exception as e:
            print(f"  [brothers] could not load {fname}: {e}")

def list_all():
    return [
        {"id": k, "name": m.NAME,
         "description": getattr(m, "DESCRIPTION", ""),
         "commands":    getattr(m, "COMMANDS", [])}
        for k, m in _brothers.items()
        if getattr(m, "ENABLED", True)
    ]

def _ordered():
    """Brothers in priority order, with any unlisted ones in the middle."""
    listed   = [k for k in PRIORITY if k in _brothers]
    unlisted = sorted(k for k in _brothers if k not in PRIORITY)
    # keep orchestrator dead last if present
    tail = []
    if "orchestrator" in listed:
        listed.remove("orchestrator")
        tail = ["orchestrator"]
    return listed + unlisted + tail

def dispatch(user_input: str):
    for key in _ordered():
        mod = _brothers[key]
        if not getattr(mod, "ENABLED", True):
            continue
        try:
            result = mod.run(user_input)
            if result is not None:
                return result, mod.NAME
        except Exception as e:
            # one brother failing must never break the conversation
            print(f"  [brothers] {mod.NAME} error: {e}")
            traceback.print_exc()
    return None, None

load_all()
