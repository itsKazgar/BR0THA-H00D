import os, requests, json

GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def think(prompt: str, fast=True) -> str:
    if GROQ_KEY:
        try:
            r = requests.post(GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                json={
                    "model": "llama3-8b-8192" if fast else "llama3-70b-8192",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.3,
                },
                timeout=15
            )
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"[groq unavailable: {e}]"
    return "[no_llm]"

def should_buy(coin: dict, score: int, reasons: list) -> dict:
    """
    Returns {"buy": True/False, "confidence": 0-100, "thesis": str, "risk": str}
    Works with or without Groq key.
    """
    # Rule-based baseline (always runs)
    rule_buy    = score >= 70
    confidence  = score

    if not GROQ_KEY:
        # Smart rule-based engine — no LLM needed
        flags   = []
        risk    = []
        penalty = 0
        bonus   = 0


        # 7. Market sentiment from learnings
        try:
            import sqlite3 as _sq
            _c = _sq.connect("core/brain.db")
            _rows = _c.execute("SELECT insight FROM learnings WHERE agent='news_scout' ORDER BY ts DESC LIMIT 3").fetchall()
            _c.close()
            _insights = " ".join([r[0] for r in _rows])
            if "extreme fear" in _insights.lower() or "bearish" in _insights.lower():
                penalty += 15
                risk.append("market: extreme fear/bearish")
            elif "bullish" in _insights.lower():
                bonus += 10
                flags.append("market: bullish sentiment")
        except:
            pass
        # 1. 5m price action — dumps are a red flag
        c5 = coin.get("change_5m", 0)
        if c5 <= -10:
            penalty += 25
            risk.append(f"dumping {c5:.1f}% in 5m")
        elif c5 <= -5:
            penalty += 12
            risk.append(f"weak 5m {c5:.1f}%")
        elif c5 >= 10:
            bonus += 10
            flags.append(f"+{c5:.1f}% 5m surge")

        # 2. Buy/sell ratio
        total = coin.get("buys_1h", 0) + coin.get("sells_1h", 1)
        ratio = coin.get("buys_1h", 0) / total
        if ratio < 0.55:
            penalty += 20
            risk.append(f"weak buy ratio {ratio:.0%}")
        elif ratio >= 0.75:
            bonus += 15
            flags.append(f"strong buyers {ratio:.0%}")

        # 3. Liquidity risk
        liq = coin.get("liquidity", 0)
        if liq < 15_000:
            penalty += 15
            risk.append(f"very thin liq ${liq:,.0f}")
        elif liq < 30_000:
            penalty += 5
            risk.append(f"thin liq ${liq:,.0f}")

        # 4. Age — scalp fresh, avoid stale
        age = coin.get("age_hrs", 99)
        if age > 12:
            penalty += 20
            risk.append(f"old coin {age:.0f}h")
        elif age < 1:
            bonus += 5
            flags.append("brand new")

        # 5. Multi-source confirmation
        sources = coin.get("sources", [])
        if len(sources) >= 3:
            bonus += 15
            flags.append("confirmed 3 sources")
        elif len(sources) >= 2:
            bonus += 8
            flags.append("confirmed 2 sources")

        # 6. 1h momentum
        c1h = coin.get("change_1h", 0)
        if c1h < 0:
            penalty += 10
            risk.append(f"1h negative {c1h:.1f}%")
        elif 5 <= c1h <= 50:
            bonus += 10
            flags.append(f"+{c1h:.1f}% 1h sweet spot")
        elif c1h > 100:
            penalty += 15
            risk.append(f"already pumped {c1h:.0f}%")

        final_confidence = max(0, min(100, score + bonus - penalty))
        smart_buy = final_confidence >= 72 and penalty < 30

        thesis = f"Rules+: {', '.join(flags[:3]) or ', '.join(reasons[:2])}"
        risk_str = ", ".join(risk[:2]) if risk else "within normal range"

        return {
            "buy":        smart_buy,
            "confidence": final_confidence,
            "thesis":     thesis,
            "risk":       risk_str,
            "mode":       "rules+"
        }

    # Load custom agent tasks from brain
    custom_context = ""
    try:
        import sqlite3
        _db = sqlite3.connect("core/brain.db")
        rows = _db.execute("SELECT name, task FROM custom_agents WHERE enabled=1").fetchall()
        _db.close()
        if rows:
            custom_context = "\nCustom agent instructions:\n" + "\n".join([f"- {r[0]}: {r[1]}" for r in rows])
    except:
        pass


    # Fetch recent market learnings
    market_context = ""
    try:
        import sqlite3 as _sq
        _c = _sq.connect("core/brain.db")
        _sent = _c.execute("SELECT insight FROM learnings WHERE agent='news_scout' ORDER BY ts DESC LIMIT 2").fetchall()
        _whal = _c.execute("SELECT insight FROM learnings WHERE agent='whale_tracker' ORDER BY ts DESC LIMIT 2").fetchall()
        _c.close()
        _lines = [r[0] for r in _sent + _whal]
        if _lines:
            market_context = "\nMarket context:\n" + "\n".join(f"- {l}" for l in _lines)
    except:
        pass
    # LLM layer (runs if Groq key present)
    prompt = f"""You are a Solana memecoin trader. Analyze this signal and decide BUY or SKIP.{custom_context}{market_context}

Coin: {coin.get('name')}
Price: ${coin.get('price')}
Market cap: ${coin.get('mcap') or 0:,.0f}
Age: {coin.get('age_hrs')} hours old
1h change: {coin.get('change_1h') or 0:+.1f}%
24h volume: ${coin.get('volume_24h') or 0:,.0f}
Liquidity: ${coin.get('liquidity') or 0:,.0f}
Buy/sell ratio 1h: {coin.get('buys_1h')} buys / {coin.get('sells_1h')} sells
Score: {score}/100
Signals: {', '.join(reasons)}

Respond in JSON only:
{{"buy": true/false, "confidence": 0-100, "thesis": "one sentence why", "risk": "one sentence main risk"}}"""

    raw = think(prompt)
    try:
        clean = raw[raw.find("{"):raw.rfind("}")+1]
        result = json.loads(clean)
        result["mode"] = "llm"
        # LLM can veto a rule-based buy or confirm it
        if not result.get("buy") and rule_buy:
            result["thesis"] = f"LLM vetoed rule signal. {result.get('thesis','')}"
        return result
    except:
        return {
            "buy":        rule_buy,
            "confidence": confidence,
            "thesis":     f"LLM parse failed, using rules: {', '.join(reasons[:2])}",
            "risk":       "Parse error",
            "mode":       "rules_fallback"
        }

def analyze_exit(coin_name: str, entry: float, current: float, age_mins: int) -> str:
    pnl = (current - entry) / entry * 100
    if not GROQ_KEY:
        return "hold"
    prompt = f"""Solana memecoin position:
Coin: {coin_name}
Entry: ${entry:.8f}  Current: ${current:.8f}  PnL: {pnl:+.1f}%
Time held: {age_mins} minutes

Should we HOLD, SELL_PARTIAL (50%), or SELL_ALL?
Reply with just one word: HOLD or SELL_PARTIAL or SELL_ALL"""
    result = think(prompt)
    r = result.strip().upper()
    if "SELL_ALL" in r:    return "sell_all"
    if "SELL_PARTIAL" in r: return "sell_partial"
    return "hold"
