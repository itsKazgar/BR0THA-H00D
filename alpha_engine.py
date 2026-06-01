"""
alpha_engine.py - BR0THA Alpha Signal Engine

Trading philosophy hardcoded into every decision:
- Scalp fast, take profit early, leave a moon bag
- Never all-in — small % of port per trade
- Profit > moon. More plays always come.
- Compound gains, stack it, build slow
- Safe exit > holding hope
"""

import requests, time, os
from dotenv import load_dotenv
load_dotenv(override=True)

HELIUS_KEY = os.getenv("HELIUS_API_KEY", "")
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

RUG_PATTERNS = ["RUGPULL", "SCAM", "FAKE", "HONEYPOT"]

BORING_SYMBOLS = {
    "USDT","USDC","DAI","BUSD","FRAX","TUSD","PYUSD","USAD","USDG","USDS","FDUSD","GUSD",
    "WBTC","CBBTC","WETH","WBNB","WMATIC",
    "AAVE","LINK","UNI","CRV","MKR","COMP","CHZ","ENA","RENDER",
    "SOL",
}

# ── TRADING PHILOSOPHY ─────────────────────────────────────────────────────────
TRADE_RULES = {
    "max_port_pct":     3.0,   # never more than 3% of portfolio per trade
    "take_profit_pct":  40.0,  # take profit at 40% gain
    "moon_bag_pct":     20.0,  # leave 20% of position as moon bag after TP
    "stop_loss_pct":   -15.0,  # cut at -15%, no hope holding
    "scalp_target":     25.0,  # minimum acceptable gain to bother entering
    "compound":         True,  # reinvest profits, stack it
}

def check_rug_risk(symbol, data):

    risk = 0
    reasons = []
    sym = symbol.upper()

    if sym in BORING_SYMBOLS:
        return {"risk_score": 100, "safe": False, "reasons": ["Not an alpha play"]}

    for pattern in RUG_PATTERNS:
        if pattern in sym:
            risk += 40
            reasons.append(f"Rug name: {pattern}")
            break

    liquidity = float(data.get("liquidity") or 0)
    if liquidity < 25000:
        risk += 40
        reasons.append(f"Dangerously low liq: ${liquidity:,.0f}")
    elif liquidity < 75000:
        risk += 15
        reasons.append(f"Low liq: ${liquidity:,.0f}")

    buys  = int(data.get("buys")  or data.get("buys_24h")  or 0)
    sells = int(data.get("sells") or data.get("sells_24h") or 0)
    total = buys + sells

    if total < 20:
        risk += 20
        reasons.append(f"Only {total} txns — thin")

    if total > 0 and sells > buys * 2.5:
        risk += 35
        reasons.append(f"Dump pattern: {sells} sells vs {buys} buys")
    elif sells > buys * 1.5:
        risk += 15
        reasons.append(f"Sell pressure: {sells} vs {buys}")

    volume = float(data.get("volume") or data.get("volume_24h") or 0)
    if volume < 10000:
        risk += 25
        reasons.append(f"Near-zero volume: ${volume:,.0f}")

    fdv = float(data.get("fdv") or 0)
    if fdv > 1000000000:
        risk += 20
        reasons.append(f"FDV ${fdv/1e6:.0f}M — limited upside")

    return {"risk_score": min(risk, 100), "safe": risk < 55, "reasons": reasons}


def get_momentum_signal(data):
    change    = float(data.get("change_24h") or data.get("price_change_24h") or 0)
    volume    = float(data.get("volume")     or data.get("volume_24h")       or 0)
    liquidity = float(data.get("liquidity")  or 0)
    buys      = int(data.get("buys")  or data.get("buys_24h")  or 0)
    sells     = int(data.get("sells") or data.get("sells_24h") or 0)

    signals = []
    score   = 0

    # Price momentum — calibrated to real meme token moves
    if change > 500:
        score += 60
        signals.append(f"🚀 Explosive: +{change:.0f}%")
    elif change > 100:
        score += 45
        signals.append(f"🔥 Strong breakout: +{change:.0f}%")
    elif change > 30:
        score += 30
        signals.append(f"📈 Good momentum: +{change:.0f}%")
    elif change > 10:
        score += 15
        signals.append(f"Rising: +{change:.1f}%")
    elif change < -20:
        score -= 25
        signals.append(f"📉 Downtrend: {change:.1f}% — risky entry")

    # Buy pressure
    total = buys + sells
    if total > 0:
        buy_pct = (buys / total) * 100
        if buy_pct > 65:
            score += 30
            signals.append(f"💪 Strong buyers: {buy_pct:.0f}% buys ({buys:,} buys)")
        elif buy_pct > 55:
            score += 15
            signals.append(f"Mild buy bias: {buy_pct:.0f}%")
        elif buy_pct < 40:
            score -= 20
            signals.append(f"Sellers winning: {buy_pct:.0f}% buys only")

    # Volume
    if volume > 1000000:
        score += 25
        signals.append(f"💰 Heavy volume: ${volume/1e6:.1f}M")
    elif volume > 500000:
        score += 18
        signals.append(f"Good volume: ${volume/1e3:.0f}K")
    elif volume > 100000:
        score += 10
        signals.append(f"Decent volume: ${volume/1e3:.0f}K")

    # Liquidity
    if liquidity > 500000:
        score += 15
        signals.append(f"Deep liq: ${liquidity/1e3:.0f}K")
    elif liquidity > 100000:
        score += 8
        signals.append(f"OK liq: ${liquidity/1e3:.0f}K")

    # Vol/liq ratio
    if liquidity > 0:
        vlr = (volume / liquidity) * 100
        if 20 <= vlr <= 300:
            score += 10
            signals.append(f"Healthy vol/liq: {vlr:.0f}%")
        elif vlr > 500:
            score -= 10
            signals.append(f"⚠️ Wash trading risk: {vlr:.0f}% vol/liq")

    # Threshold: 35 is enough — catches real moves without being too strict
    return {"momentum_score": max(score, 0), "strong": score >= 35, "signals": signals}


def build_thesis(symbol, data, rug, momentum):
    change    = float(data.get("change_24h") or data.get("price_change_24h") or 0)
    volume    = float(data.get("volume")     or data.get("volume_24h")       or 0)
    liquidity = float(data.get("liquidity")  or 0)
    buys      = int(data.get("buys")  or data.get("buys_24h")  or 0)
    sells     = int(data.get("sells") or data.get("sells_24h") or 0)
    price     = data.get("price") or "?"
    fdv       = float(data.get("fdv") or 0)
    buy_pct   = (buys / max(buys + sells, 1)) * 100

    bull = []
    bear = []

    if change > 50:  bull.append(f"+{change:.0f}% — momentum is real")
    if change > 10:  bull.append(f"Uptrend confirmed: +{change:.1f}%")
    if buy_pct > 60: bull.append(f"{buy_pct:.0f}% of trades are buys — accumulation")
    if volume > 500000: bull.append(f"${volume/1e3:.0f}K volume — capital flowing in")
    if liquidity > 200000: bull.append(f"${liquidity/1e3:.0f}K liq — safe to size in/out")
    if rug["risk_score"] < 25: bull.append(f"Clean rug score {rug['risk_score']}/100")

    if change < 0:   bear.append(f"Negative 24h: {change:.1f}%")
    if buy_pct < 50: bear.append(f"Sellers have edge: {buy_pct:.0f}% buys")
    if liquidity < 100000: bear.append(f"Thin liq ${liquidity/1e3:.0f}K — slippage risk")
    if fdv > 100000000: bear.append(f"FDV ${fdv/1e6:.0f}M — supply overhang")
    if rug["reasons"]: bear.append(f"Flags: {'; '.join(rug['reasons'][:2])}")

    # Trading plan using the philosophy
    plan = (
        f"Entry: small size ({TRADE_RULES['max_port_pct']}% max port). "
        f"TP at +{TRADE_RULES['take_profit_pct']:.0f}%, keep {TRADE_RULES['moon_bag_pct']:.0f}% as moon bag. "
        f"Stop at {TRADE_RULES['stop_loss_pct']:.0f}%. Scalp first, compound profits."
    )

    return {
        "summary": f"{symbol}: {momentum['signals'][0] if momentum['signals'] else 'signals mixed'}",
        "bull_case": bull,
        "bear_case": bear,
        "trade_plan": plan,
        "key_stats": {
            "price": price,
            "change_24h": f"{change:+.1f}%",
            "volume": f"${volume/1e3:.0f}K",
            "liquidity": f"${liquidity/1e3:.0f}K",
            "buy_pressure": f"{buy_pct:.0f}% buys",
            "rug_score": f"{rug['risk_score']}/100",
            "momentum": f"{momentum['momentum_score']}/100",
        }
    }


def analyze_token(symbol, data):
    rug      = check_rug_risk(symbol, data)
    momentum = get_momentum_signal(data)

    if not rug["safe"]:
        return {"token": symbol, "action": "REJECT",
                "reason": "; ".join(rug["reasons"][:2]),
                "rug_score": rug["risk_score"], "momentum_score": momentum["momentum_score"]}

    if not momentum["strong"]:
        return {"token": symbol, "action": "WATCH",
                "reason": f"Momentum {momentum['momentum_score']}/100 — not there yet. Signals: {momentum['signals']}",
                "rug_score": rug["risk_score"], "momentum_score": momentum["momentum_score"],
                "signals": momentum["signals"]}

    thesis = build_thesis(symbol, data, rug, momentum)
    return {"token": symbol, "action": "DEBATE",
            "reason": thesis["summary"],
            "rug_score": rug["risk_score"], "momentum_score": momentum["momentum_score"],
            "signals": momentum["signals"], "thesis": thesis, "token_data": data,
            "trade_rules": TRADE_RULES}


def filter_market(market_list):
    approved, watching, rejected = [], [], []
    for token in market_list:
        result = analyze_token(token["token"], token)
        result["market_data"] = token
        if result["action"] == "DEBATE":
            approved.append(result)
            print(f"  ✅ APPROVED: {token['token']:12} | rug={result['rug_score']:3}/100 | momentum={result['momentum_score']}/100 | {result['reason']}")
        elif result["action"] == "WATCH":
            watching.append(result)
            print(f"  👁  WATCH:   {token['token']:12} | momentum={result['momentum_score']}/100")
        else:
            rejected.append(result)
            print(f"  ❌ REJECTED: {token['token']:12} | {result['reason']}")
    return approved, watching, rejected


if __name__ == "__main__":
    from scanner import build_market
    print("Running full alpha pipeline...\n")
    market = build_market()
    print(f"\n{len(market)} tokens from scanner — filtering...\n")
    approved, watching, rejected = filter_market(market)
    print(f"\n{'='*55}")
    print(f"  {len(approved)} for debate | {len(watching)} watching | {len(rejected)} rejected")
    print(f"{'='*55}")
    for a in approved:
        t = a.get("thesis", {})
        print(f"\n  🎯 {a['token']}")
        print(f"     {t.get('summary','')}")
        print(f"     BULL: {' | '.join(t.get('bull_case',[]))}")
        print(f"     BEAR: {' | '.join(t.get('bear_case',[]))}")
        print(f"     PLAN: {t.get('trade_plan','')}")

# Patch: rugcheck integration (appended)
_original_check_rug_risk = check_rug_risk

def check_rug_risk(symbol, data):
    # If rugcheck.xyz score available, use it as primary signal
    rugcheck = data.get("rugcheck", {})
    rc_score = rugcheck.get("score", 0)
    if rc_score > 700:
        return {"risk_score": 95, "safe": False,
                "reasons": [f"Rugcheck.xyz score {rc_score} — DANGEROUS"]}
    result = _original_check_rug_risk(symbol, data)
    if rc_score > 400:
        result["risk_score"] = min(result["risk_score"] + 20, 100)
        result["reasons"].append(f"Rugcheck.xyz score {rc_score} — elevated risk")
        result["safe"] = result["risk_score"] < 55
    elif rc_score > 0 and rc_score < 200:
        result["risk_score"] = max(result["risk_score"] - 10, 0)
        result["reasons"].append(f"✅ Rugcheck.xyz score {rc_score} — low risk")
        result["safe"] = result["risk_score"] < 55
    return result
