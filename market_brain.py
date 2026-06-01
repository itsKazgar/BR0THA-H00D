from market_hub import build_market_view


def build_market_context():

    market = build_market_view()

    lines = []

    lines.append("\n=== LIVE SOLANA MARKET ===\n")

    # ── DEX FLOW ─────────────────────────

    lines.append("TOP DEX FLOW:")

    for x in market.get("dexscreener", [])[:5]:

        try:

            lines.append(
                f"- {x['token']} | "
                f"24h {x['change_24h']}% | "
                f"Vol ${x['volume_24h']} | "
                f"Liq ${x['liquidity']}"
            )
        except:
            pass

    # ── COINGECKO ────────────────────────

    lines.append("\nTRENDING COINS:")

    for x in market.get("coingecko", [])[:3]:

        try:

            lines.append(
                f"- {x['name']} ({x['token']}) "
                f"rank #{x['market_cap_rank']}"
            )
        except:
            pass

    # ── PUMPFUN ──────────────────────────

    lines.append("\nPUMPFUN MOMENTUM:")

    for x in market.get("pumpfun", [])[:3]:

        try:

            lines.append(
                f"- {x['token']} | "
                f"MCAP ${x['market_cap']} | "
                f"VOL ${x['volume']}"
            )
        except:
            pass

    return "\n".join(lines)


if __name__ == "__main__":

    print(build_market_context())
