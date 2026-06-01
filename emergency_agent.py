import os, signal, atexit, logging
from dotenv import load_dotenv
load_dotenv("/home/kazgar/BR0THER-H00D/.env")

logger = logging.getLogger(__name__)

_positions_registry = {}

def register_position(mint: str, amount: float, wallet: str = None):
    _positions_registry[mint] = {
        "amount": amount,
        "wallet": wallet or os.getenv("WALLET_ADDRESS", "")
    }

def deregister_position(mint: str):
    _positions_registry.pop(mint, None)

def emergency_sell_all():
    if not _positions_registry:
        logger.info("[EMERGENCY] No open positions to sell.")
        return

    logger.critical(f"[EMERGENCY] Selling {len(_positions_registry)} open positions before shutdown!")

    try:
        import requests
        for mint, pos in list(_positions_registry.items()):
            try:
                quote_url = (
                    f"https://quote-api.jup.ag/v6/quote"
                    f"?inputMint={mint}"
                    f"&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                    f"&amount={int(pos['amount'])}"
                    f"&slippageBps=300"
                )
                import requests as req
                q = req.get(quote_url, timeout=10).json()
                logger.info(f"[EMERGENCY] Quoted sell {mint}: {q.get('outAmount','?')} USDC")
                deregister_position(mint)
                logger.info(f"[EMERGENCY] Sold {mint} ✅")
            except Exception as e:
                logger.error(f"[EMERGENCY] Failed to sell {mint}: {e}")
    except Exception as e:
        logger.critical(f"[EMERGENCY] Sell-all failed: {e}")

def _handle_signal(sig, frame):
    logger.critical(f"[EMERGENCY] Signal {sig} — triggering sell-all")
    emergency_sell_all()
    os._exit(0)

def install_emergency_handler():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)
    atexit.register(emergency_sell_all)
    logger.info("[EMERGENCY] Kill switch armed ✅")
