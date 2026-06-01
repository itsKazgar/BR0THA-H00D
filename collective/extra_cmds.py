from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

async def cmd_wallet(update, context):
    uid = str(update.effective_user.id)
    ensure_user(uid)
    w = get_user_wallet(uid)
    if not w:
        await update.message.reply_text("No wallet found. Type: create wallet")
        return
    addr = w["address"]
    data = get_solana_balance_helius(addr)
    if data.get("ok"):
        tok = "\n".join("  " + k + ": " + str(v) for k,v in list(data["tokens"].items())[:10]) or "  None"
        msg = "Your Wallet\n" + addr + "\n\nSOL: " + str(data["SOL"]) + "\n\nTokens:\n" + tok
    else:
        msg = "Your Wallet\n" + addr + "\n\nCould not fetch balance."
    await update.message.reply_text(msg)

async def cmd_trades(update, context):
    uid = str(update.effective_user.id)
    ensure_user(uid)
    if not TRADING_ENABLED:
        await update.message.reply_text("Trading not available.")
        return
    positions = get_open_positions(uid)
    if not positions:
        await update.message.reply_text("No open trades. Use Buy Token to open one.")
        return
    lines = ["Open Trades\n" + "-"*20]
    for p in positions:
        pnl = get_position_pnl(p)
        lines.append(p["symbol"] + " | Entry: " + str(p["entry_price"]) + " | PnL: " + str(pnl["pnl_pct"]) + "%")
    await update.message.reply_text("\n".join(lines))

async def cmd_tools(update, context):
    uid = str(update.effective_user.id)
    ensure_user(uid)
    kb = [
        [InlineKeyboardButton("Buy Token", callback_data="wizard_buy"),
         InlineKeyboardButton("My Trades", callback_data="dash_portfolio")],
        [InlineKeyboardButton("My Wallet", callback_data="dash_portfolio"),
         InlineKeyboardButton("Market", callback_data="dash_market")],
        [InlineKeyboardButton("Set Alert", callback_data="wizard_alert"),
         InlineKeyboardButton("DCA Plan", callback_data="dash_dca")],
        [InlineKeyboardButton("Gift Cards", callback_data="dash_giftcards"),
         InlineKeyboardButton("X402 Pay", callback_data="dash_x402")],
        [InlineKeyboardButton("AI Brain", callback_data="dash_system"),
         InlineKeyboardButton("Private Send", callback_data="wizard_private")],
    ]
    await update.message.reply_text(
        "BR0THA Tools - Pick a tool or just chat!",
        reply_markup=InlineKeyboardMarkup(kb)
    )
