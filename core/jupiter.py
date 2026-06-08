import os, requests, base64, json

JUPITER_QUOTE = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP  = "https://api.jup.ag/swap/v1/swap"
RPC_URL       = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
USDC_MINT     = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT      = "So11111111111111111111111111111111111111112"
USDC_DECIMALS = 6

def get_quote(input_mint: str, output_mint: str, amount_usd: float, slippage_bps=3000, input_decimals=6):
    try:
        # If input is SOL, convert USD -> SOL -> lamports (9 decimals)
        # If input is a token, amount is already raw token count, just apply decimals
        if input_mint == SOL_MINT:
            try:
                r2 = requests.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                    timeout=5)
                sol_price = float(r2.json()["solana"]["usd"])
                sol_amount = amount_usd / sol_price
                amount_raw = int(sol_amount * (10 ** 9))
            except Exception:
                return None, "could not fetch SOL price for conversion"
        else:
            amount_raw = int(amount_usd * (10 ** input_decimals))

        if amount_raw <= 0:
            return None, f"amount_raw={amount_raw} too small"

        r = requests.get(JUPITER_QUOTE, params={
            "inputMint":   input_mint,
            "outputMint":  output_mint,
            "amount":      amount_raw,
            "slippageBps": slippage_bps,
        }, timeout=10)
        data = r.json()
        if "error" in data:
            return None, data["error"]
        return data, None
    except Exception as e:
        return None, str(e)

def execute_swap(wallet_keypair, quote_response: dict) -> dict:
    """
    wallet_keypair: solders Keypair object
    Returns {"success": bool, "tx": str, "error": str}
    """
    try:
        from solders.keypair import Keypair
        from solders.transaction import VersionedTransaction
        import base64

        pubkey = str(wallet_keypair.pubkey())
        body = {
            "quoteResponse":            quote_response,
            "userPublicKey":            pubkey,
            "wrapAndUnwrapSol":         True,
            "dynamicComputeUnitLimit":  True,
            "prioritizationFeeLamports": "auto",
        }
        r = requests.post(JUPITER_SWAP, json=body, timeout=15)
        swap_data = r.json()
        if "error" in swap_data:
            return {"success": False, "tx": "", "error": swap_data["error"]}

        tx_bytes  = base64.b64decode(swap_data["swapTransaction"])
        tx        = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = wallet_keypair.sign_message(bytes(tx.message)); signed_tx = VersionedTransaction(tx.message, [wallet_keypair])

        # Send to RPC
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method":  "sendTransaction",
            "params":  [
                base64.b64encode(bytes(signed_tx)).decode(),
                {"encoding": "base64", "skipPreflight": False,
                 "preflightCommitment": "confirmed"}
            ]
        }
        rpc_r = requests.post(RPC_URL, json=payload, timeout=30)
        result = rpc_r.json()
        if "error" in result:
            return {"success": False, "tx": "", "error": str(result["error"])}
        tx_sig = result.get("result", "")
        return {"success": True, "tx": tx_sig, "error": ""}

    except Exception as e:
        return {"success": False, "tx": "", "error": str(e)}

def get_wallet_balance(pubkey: str) -> dict:
    """Returns SOL and USDC balances"""
    try:
        # SOL balance
        r = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getBalance",
            "params": [pubkey]
        }, timeout=10)
        sol = r.json().get("result", {}).get("value", 0) / 1e9

        # USDC balance
        r2 = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [pubkey,
                {"mint": USDC_MINT},
                {"encoding": "jsonParsed"}
            ]
        }, timeout=10)
        accounts = r2.json().get("result", {}).get("value", [])
        usdc = 0
        if accounts:
            usdc = float(accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)

        return {"sol": round(sol, 4), "usdc": round(usdc, 2)}
    except Exception as e:
        return {"sol": 0, "usdc": 0, "error": str(e)}
