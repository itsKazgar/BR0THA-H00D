#!/usr/bin/env python3
"""Quick health check — run this anytime to confirm nothing's broken."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    from brothers import load_all, _brothers, _ordered
    load_all()
    print(f"🔺 BR0THER-H00D smoke test\n")
    print(f"  {len(_brothers)} brothers loaded\n")

    fails = 0
    for name in _ordered():
        mod = _brothers[name]
        try:
            mod.run("___noop___")  # should return None, not crash
            print(f"  ok    {name}")
        except Exception as e:
            print(f"  CRASH {name}: {e}")
            fails += 1

    # check core systems
    print()
    try:
        from core import brain, council
        brain.recall(limit=1)
        council.read_tome(limit=1)
        print("  ok    core/brain")
        print("  ok    core/council")
    except Exception as e:
        print(f"  CRASH core: {e}")
        fails += 1

    print()
    if fails == 0:
        print("✅ all systems healthy")
        return 0
    print(f"❌ {fails} issue(s) found")
    return 1

if __name__ == "__main__":
    sys.exit(main())
