"""
intel_feed.py — Feeds live market data into the council before voting.
Pulls from pump.fun, DexScreener, CoinGecko, social scanner, whale tracker.
Call build_context() to get a rich prompt injection for any agent.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ── Safe imports (graceful fallback if a scanner fails) ───────────────────────

def _try(fn, *args, default=None, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning(f"[FEED] {fn.__name__} failed: {e}")
        return default

# ── Individual feed pullers ───────────────────────────────────────────────────

def get_pump_alpha():
    from pump_scanner import get_new_pump_tokens, get_graduated_tokens
    new_tokens = _try(get_new_pump_tokens, limit=5, default=[])
    graduated  = _try(get_graduated_tokens, limit=3, default=[])
    lines = []
    if graduated:
        lines.append("🎓 GRADUATED (pump→Raydium):")
        for t in graduated:
            lines.append(f"  ${t.get('token','?')} | mcap ${t.get('market_cap',0):,.0f} | {t.get('name','')}")
    if new_tokens:
        lines.append("🆕 NEW LAUNCHES:")
        for t in new_tokens[:5]:
            lines.append(f"  ${t.get('token','?')} | mcap ${t.get('market_cap',0):,.0f} | {t.get('description','')[:60]}")
    return "\n".join(lines) if lines else None

def get_sol_price():
    from market_data import fetch_token_data
    d = _try(fetch_token_data, "SOL", default={})
    if not d or "error" in d:
        return None
    return (
        f"SOL: ${d.get('price','?')} | "
        f"vol24h ${float(d.get('volume_24h') or 0):,.0f} | "
        f"liq ${float(d.get('liquidity') or 0):,.0f}"
    )

def get_trending_tokens():
    from market_data import fetch_token_data
    import requests
    lines = []
    try:
        # GeckoTerminal trending on Solana — free, no key
        r = requests.get(
            "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools",
            headers={"Accept": "application/json"}, timeout=10
        )
        pools = r.json().get("data", [])[:5]
        lines.append("🔥 TRENDING (GeckoTerminal):")
        for p in pools:
            attr = p.get("attributes", {})
            name = attr.get("name", "?")
            price = attr.get("base_token_price_usd", "?")
            vol   = attr.get("volume_usd", {}).get("h24", "?")
            lines.append(f"  {name} | ${price} | vol24h ${float(vol or 0):,.0f}")
    except Exception as e:
        logger.warning(f"[FEED] trending failed: {e}")
    return "\n".join(lines) if lines else None

def get_social_signals():
    from social_scanner import scan_social
    signals = _try(scan_social, default=[])
    if not signals:
        return None
    lines = ["📡 CT SIGNALS:"]
    for s in signals[:5]:
        weight = s.get("weight", 0)
        handle = s.get("account", "?")
        tokens = s.get("tokens", [])
        cas    = s.get("cas", [])
        text   = s.get("text", "")[:80]
        if tokens or cas:
            lines.append(f"  @{handle} (weight {weight}): {tokens} {cas} — {text}")
    return "\n".join(lines) if len(lines) > 1 else None

def get_whale_moves():
    try:
        from whale_tracker import get_recent_whale_moves
        moves = _try(get_recent_whale_moves, default=[])
        if not moves:
            return None
        lines = ["🐋 WHALE MOVES:"]
        for m in moves[:4]:
            lines.append(
                f"  {m.get('type','?')} ${m.get('token','?')} "
                f"${m.get('amount_usd',0):,.0f} — {m.get('wallet','')[:8]}..."
            )
        return "\n".join(lines)
    except Exception:
        return None

# ── Main context builder ──────────────────────────────────────────────────────

def build_context(token: str = None, timeout: int = 12) -> str:
    """
    Runs all feed pullers in parallel.
    Returns a formatted string to inject into agent system prompts.
    token: optional specific token to enrich with DexScreener data
    """
    tasks = {
        "sol":      get_sol_price,
        "pump":     get_pump_alpha,
        "trending": get_trending_tokens,
        "social":   get_social_signals,
        "whales":   get_whale_moves,
    }

    results = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures, timeout=timeout):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                logger.warning(f"[FEED] {key} timed out or failed: {e}")

    # Optional: enrich specific token
    token_block = ""
    if token:
        try:
            from market_data import fetch_token_data
            d = _try(fetch_token_data, token, default={})
            if d and "error" not in d:
                token_block = (
                    f"\n🎯 TOKEN: {token}\n"
                    f"  Price: ${d.get('price','?')}\n"
                    f"  Vol24h: ${float(d.get('volume_24h') or 0):,.0f}\n"
                    f"  Liquidity: ${float(d.get('liquidity') or 0):,.0f}\n"
                    f"  FDV: ${float(d.get('fdv') or 0):,.0f}\n"
                )
        except Exception:
            pass

    sections = [v for v in results.values() if v]
    if not sections and not token_block:
        return ""

    header = f"\n{'─'*50}\n📊 LIVE MARKET INTEL ({time.strftime('%H:%M UTC')})\n{'─'*50}\n"
    body   = "\n\n".join(sections)
    return header + body + token_block + f"\n{'─'*50}\n"


if __name__ == "__main__":
    print("Testing intel feed...\n")
    ctx = build_context()
    print(ctx if ctx else "No data returned — check scanner files")
