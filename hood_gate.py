"""
hood_gate.py — $H00D Token Gate
Checks if a wallet holds enough $H00D tokens to access BR0THER-H00D
"""

import os, httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── Config — paste your $H00D mint address in .env as HOOD_MINT ──────────────
HOOD_MINT        = os.getenv("HOOD_MINT", "")
HOOD_MIN_BALANCE = int(os.getenv("HOOD_MIN_BALANCE", "100000"))   # min tokens to hold
HOOD_FEE_AMOUNT  = int(os.getenv("HOOD_FEE_AMOUNT",  "1000"))     # fee per session in $H00D
HELIUS_KEY       = os.getenv("HELIUS_API_KEY", "")
RPC_URL          = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}" if HELIUS_KEY \
                   else "https://api.mainnet-beta.solana.com"

class GateRequest(BaseModel):
    wallet: str

def get_hood_balance(wallet: str) -> float:
    """Check how many $H00D tokens a wallet holds via Helius RPC"""
    if not HOOD_MINT:
        return 0.0
    try:
        r = httpx.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"mint": HOOD_MINT},
                {"encoding": "jsonParsed"}
            ]
        }, timeout=10)
        accounts = r.json().get("result", {}).get("value", [])
        if not accounts:
            return 0.0
        amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
        return float(amount or 0)
    except Exception as e:
        print(f"[hood_gate] balance check error: {e}")
        return 0.0

@router.post("/gate/check")
def gate_check(req: GateRequest):
    """Check if wallet can access — must hold HOOD_MIN_BALANCE tokens"""
    if not HOOD_MINT:
        return {"access": True, "balance": 0, "note": "gate not configured yet — set HOOD_MINT in .env"}
    balance = get_hood_balance(req.wallet)
    access  = balance >= HOOD_MIN_BALANCE
    return {
        "access":      access,
        "balance":     balance,
        "required":    HOOD_MIN_BALANCE,
        "fee":         HOOD_FEE_AMOUNT,
        "mint":        HOOD_MINT,
        "wallet":      req.wallet[:6] + "..." + req.wallet[-4:],
        "message":     "access granted" if access else f"need {HOOD_MIN_BALANCE:,} $H00D, you have {balance:,.0f}",
    }

@router.get("/gate/config")
def gate_config():
    """Public config — what does the gate require?"""
    return {
        "mint":         HOOD_MINT,
        "min_balance":  HOOD_MIN_BALANCE,
        "fee":          HOOD_FEE_AMOUNT,
        "configured":   bool(HOOD_MINT),
    }
