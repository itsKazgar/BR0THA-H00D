"""
intel_engine.py — BR0THA Real-Time Intelligence
================================================
Free sources, no API keys needed:
- X/CT via Nitter scraping (top Solana accounts)
- Crypto news via RSS (CoinDesk, Decrypt, The Block)
- Pump.fun new launches
- DexScreener trending
- On-chain data via Helius
- Memory DB — learns and adapts over time
"""

import os, sqlite3, json, time, asyncio, logging, requests, httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger   = logging.getLogger(__name__)
DB_PATH  = "data/agent.db"

# ── SOLANA CT ACCOUNTS TO TRACK ───────────────────────────────────────────────
CT_ACCOUNTS = [
    "Overdose_Crypto", "gainzy222", "Threadguy", "RasmrCrypto",
    "weremeow", "blknoiz06", "solanalegend", "0xMert_",
    "aeyakovenko", "rajgokal", "therealchaseeb", "jacobvcreech",
    "solanafndn", "JupiterExchange", "heliuslabs",
]

NEWS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss.xml",
    "https://cointelegraph.com/rss",
]

NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.lucabased.xyz",
]

# ── DB SETUP ──────────────────────────────────────────────────────────────────
def init_intel_tables():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS intel_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            category TEXT,
            content TEXT,
            tokens_mentioned TEXT DEFAULT '[]',
            sentiment REAL DEFAULT 0,
            importance REAL DEFAULT 0,
            ts REAL DEFAULT (unixepoch())
        );
        CREATE TABLE IF NOT EXISTS ct_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT,
            content TEXT,
            tokens_mentioned TEXT DEFAULT '[]',
            engagement INTEGER DEFAULT 0,
            ts REAL DEFAULT (unixepoch())
        );
        CREATE TABLE IF NOT EXISTS narrative_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            narrative TEXT UNIQUE,
            strength REAL DEFAULT 0,
            mentions INTEGER DEFAULT 0,
            last_seen REAL DEFAULT (unixepoch()),
            tokens TEXT DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT,
            pattern_data TEXT,
            success_rate REAL DEFAULT 0,
            sample_size INTEGER DEFAULT 0,
            ts REAL DEFAULT (unixepoch())
        );
        """)

# ── X/CT SCRAPER ──────────────────────────────────────────────────────────────
def scrape_nitter(account: str, limit: int = 5) -> list:
    """Scrape tweets from a CT account via Nitter — no API key needed."""
    for instance in NITTER_INSTANCES:
        try:
            url  = f"{instance}/{account}"
            r    = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (compatible; bot)"
            })
            if r.status_code != 200:
                continue
            soup   = BeautifulSoup(r.text, "html.parser")
            tweets = soup.select(".tweet-content")[:limit]
            results = []
            for t in tweets:
                text = t.get_text(strip=True)
                if len(text) > 10:
                    results.append({"account": account, "text": text, "source": instance})
            if results:
                return results
        except Exception as e:
            logger.debug(f"Nitter {instance} failed for {account}: {e}")
            continue
    return []

async def scan_ct(accounts: list = None, limit_per: int = 3) -> list:
    """Scan all CT accounts and store signals."""
    accounts = accounts or CT_ACCOUNTS
    all_signals = []

    for account in accounts:
        try:
            tweets = scrape_nitter(account, limit_per)
            for tweet in tweets:
                tokens = extract_token_mentions(tweet["text"])
                sentiment = quick_sentiment(tweet["text"])

                with sqlite3.connect(DB_PATH) as db:
                    # Avoid duplicates
                    exists = db.execute(
                        "SELECT id FROM ct_signals WHERE account=? AND content=?",
                        (account, tweet["text"][:200])
                    ).fetchone()
                    if not exists:
                        db.execute(
                            "INSERT INTO ct_signals (account,content,tokens_mentioned,sentiment) VALUES (?,?,?,?)",
                            (account, tweet["text"][:500], json.dumps(tokens), sentiment)
                        )
                        all_signals.append({
                            "account": account,
                            "text": tweet["text"],
                            "tokens": tokens,
                            "sentiment": sentiment,
                        })
            await asyncio.sleep(1)  # be polite
        except Exception as e:
            logger.error(f"CT scan error for {account}: {e}")

    update_narratives(all_signals)
    return all_signals

# ── NEWS SCRAPER ──────────────────────────────────────────────────────────────
def fetch_rss(url: str, limit: int = 5) -> list:
    """Fetch and parse an RSS feed."""
    try:
        import feedparser
        feed  = feedparser.parse(url)
        items = []
        for entry in feed.entries[:limit]:
            items.append({
                "title":   entry.get("title", ""),
                "summary": entry.get("summary", "")[:300],
                "link":    entry.get("link", ""),
                "ts":      entry.get("published", ""),
            })
        return items
    except Exception as e:
        logger.error(f"RSS error {url}: {e}")
        return []

async def scan_news(limit: int = 5) -> list:
    """Scan all news feeds and store in memory."""
    all_news = []
    for feed_url in NEWS_FEEDS:
        items = fetch_rss(feed_url, limit)
        for item in items:
            text   = f"{item['title']} {item['summary']}"
            tokens = extract_token_mentions(text)
            sentiment = quick_sentiment(text)

            with sqlite3.connect(DB_PATH) as db:
                exists = db.execute(
                    "SELECT id FROM intel_memory WHERE content LIKE ?",
                    (f"%{item['title'][:50]}%",)
                ).fetchone()
                if not exists:
                    db.execute(
                        "INSERT INTO intel_memory (source,category,content,tokens_mentioned,sentiment,importance) VALUES (?,?,?,?,?,?)",
                        (feed_url, "news", text[:500], json.dumps(tokens), sentiment, score_importance(text))
                    )
                    all_news.append({**item, "tokens": tokens, "sentiment": sentiment})

    return all_news

# ── PUMP.FUN SCANNER ──────────────────────────────────────────────────────────
async def scan_pumpfun(limit: int = 20) -> list:
    """Get newest pump.fun launches."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://frontend-api.pump.fun/coins?offset=0&limit=20&sort=created_timestamp&order=DESC&includeNsfw=false"
            )
        coins = r.json()
        results = []
        for coin in coins[:limit]:
            results.append({
                "mint":       coin.get("mint", ""),
                "symbol":     coin.get("symbol", "?"),
                "name":       coin.get("name", ""),
                "desc":       coin.get("description", "")[:100],
                "mcap":       float(coin.get("usd_market_cap", 0)),
                "reply_count":coin.get("reply_count", 0),
                "ts":         coin.get("created_timestamp", 0),
            })

            # Store in memory
            with sqlite3.connect(DB_PATH) as db:
                db.execute(
                    "INSERT OR IGNORE INTO intel_memory (source,category,content,tokens_mentioned,importance) VALUES (?,?,?,?,?)",
                    ("pump.fun", "launch", f"{coin.get('name')} ({coin.get('symbol')}): {coin.get('description','')[:100]}",
                     json.dumps([coin.get("symbol","")]), score_importance(coin.get("description","") + coin.get("name","")))
                )
        return results
    except Exception as e:
        logger.error(f"Pump.fun scan error: {e}")
        return []

# ── NARRATIVE DETECTOR ────────────────────────────────────────────────────────
NARRATIVE_KEYWORDS = {
    "AI agents":      ["ai agent","autonomous","llm","gpt","claude","openai","artificial intelligence"],
    "DeSci":          ["desci","science","research","bio","protein","drug","molecule"],
    "RWA":            ["real world asset","rwa","tokenized","property","gold","commodity"],
    "DePIN":          ["depin","physical infrastructure","network","node","mining","hardware"],
    "memecoins":      ["meme","dog","cat","pepe","wojak","frog","shib","doge"],
    "gaming":         ["game","gaming","play","nft game","metaverse","guild"],
    "LST/DeFi":       ["liquid staking","lst","yield","defi","apy","apr","vault"],
    "privacy":        ["privacy","anonymous","mixer","zero knowledge","zk","tor"],
    "Solana ecosystem":["solana","sol","jup","jupiter","raydium","orca","helium"],
}

def update_narratives(signals: list):
    """Detect and update narrative trends from signals."""
    text_blob = " ".join([s.get("text","") for s in signals]).lower()

    for narrative, keywords in NARRATIVE_KEYWORDS.items():
        mentions = sum(text_blob.count(kw) for kw in keywords)
        if mentions > 0:
            with sqlite3.connect(DB_PATH) as db:
                existing = db.execute(
                    "SELECT id, mentions, strength FROM narrative_trends WHERE narrative=?",
                    (narrative,)
                ).fetchone()
                if existing:
                    new_mentions  = existing[1] + mentions
                    new_strength  = min(existing[2] + (mentions * 0.1), 10.0)
                    db.execute(
                        "UPDATE narrative_trends SET mentions=?, strength=?, last_seen=? WHERE narrative=?",
                        (new_mentions, new_strength, time.time(), narrative)
                    )
                else:
                    db.execute(
                        "INSERT INTO narrative_trends (narrative,strength,mentions,last_seen) VALUES (?,?,?,?)",
                        (narrative, mentions * 0.1, mentions, time.time())
                    )

def get_hot_narratives(limit: int = 5) -> list:
    """Get currently trending narratives."""
    cutoff = time.time() - (24 * 3600)  # last 24h
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT narrative, strength, mentions FROM narrative_trends WHERE last_seen > ? ORDER BY strength DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
    return [{"narrative": r[0], "strength": round(r[1], 2), "mentions": r[2]} for r in rows]

# ── HELPERS ───────────────────────────────────────────────────────────────────
def extract_token_mentions(text: str) -> list:
    """Extract $TOKEN mentions and known token names from text."""
    import re
    tokens = re.findall(r'\$([A-Z]{2,10})', text.upper())
    known  = ["SOL","BTC","ETH","BONK","WIF","JUP","PYTH","BODEN","MEME","POPCAT","BROTHA"]
    for k in known:
        if k in text.upper() and k not in tokens:
            tokens.append(k)
    return list(set(tokens))

def quick_sentiment(text: str) -> float:
    """Simple keyword sentiment score -1 to +1."""
    text = text.lower()
    bullish = ["pump","moon","bullish","buy","gem","alpha","up","green","launch","explode","100x","send","lfg","gm"]
    bearish = ["dump","rug","scam","down","sell","bearish","dead","over","rekt","exit","fraud","warning"]
    score = sum(1 for w in bullish if w in text) - sum(1 for w in bearish if w in text)
    return max(-1.0, min(1.0, score / 5))

def score_importance(text: str) -> float:
    """Score how important/relevant a piece of intel is."""
    text = text.lower()
    signals = ["solana","sol","pump","launch","new","alpha","gem","buy","moon","100x","breaking","just in"]
    return min(sum(0.5 for s in signals if s in text), 5.0)

# ── MEMORY CONTEXT ────────────────────────────────────────────────────────────
def get_recent_intel(hours: int = 6, limit: int = 10) -> str:
    """Get recent intel formatted as context for the AI council."""
    cutoff = time.time() - (hours * 3600)

    with sqlite3.connect(DB_PATH) as db:
        news = db.execute(
            "SELECT content, sentiment FROM intel_memory WHERE ts > ? ORDER BY importance DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        ct = db.execute(
            "SELECT account, content, sentiment FROM ct_signals WHERE ts > ? ORDER BY ts DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()

    narratives = get_hot_narratives(5)

    lines = ["=== LIVE MARKET INTEL ===\n"]

    if narratives:
        lines.append("🔥 HOT NARRATIVES:")
        for n in narratives:
            lines.append(f"  • {n['narrative']} (strength {n['strength']}, {n['mentions']} mentions)")
        lines.append("")

    if ct:
        lines.append("🐦 CT SIGNALS:")
        for row in ct[:5]:
            sentiment_tag = "📈" if row[2] > 0.2 else "📉" if row[2] < -0.2 else "➡️"
            lines.append(f"  {sentiment_tag} @{row[0]}: {row[1][:120]}")
        lines.append("")

    if news:
        lines.append("📰 CRYPTO NEWS:")
        for row in news[:5]:
            lines.append(f"  • {row[0][:120]}")

    return "\n".join(lines)

def get_token_buzz(symbol: str) -> dict:
    """Check how much buzz a token has in recent intel."""
    cutoff = time.time() - (24 * 3600)
    with sqlite3.connect(DB_PATH) as db:
        ct_mentions = db.execute(
            "SELECT COUNT(*) FROM ct_signals WHERE tokens_mentioned LIKE ? AND ts > ?",
            (f'%"{symbol}"%', cutoff)
        ).fetchone()[0]
        news_mentions = db.execute(
            "SELECT COUNT(*) FROM intel_memory WHERE tokens_mentioned LIKE ? AND ts > ?",
            (f'%"{symbol}"%', cutoff)
        ).fetchone()[0]
        sentiments = db.execute(
            "SELECT sentiment FROM ct_signals WHERE tokens_mentioned LIKE ? AND ts > ?",
            (f'%"{symbol}"%', cutoff)
        ).fetchall()

    avg_sentiment = sum(r[0] for r in sentiments) / max(len(sentiments), 1)
    return {
        "symbol":        symbol,
        "ct_mentions":   ct_mentions,
        "news_mentions": news_mentions,
        "total_buzz":    ct_mentions + news_mentions,
        "sentiment":     round(avg_sentiment, 2),
        "hot":           (ct_mentions + news_mentions) >= 3,
    }

# ── FULL INTEL SCAN ───────────────────────────────────────────────────────────
async def run_full_intel_scan(bot=None, notify_user_id: str = None) -> dict:
    """
    Run everything: CT, news, pump.fun.
    Called by background job every 15 minutes.
    """
    logger.info("Running full intel scan...")
    init_intel_tables()

    ct_signals  = await scan_ct()
    news_items  = await scan_news()
    pump_coins  = await scan_pumpfun()
    narratives  = get_hot_narratives(5)

    summary = {
        "ct_signals":  len(ct_signals),
        "news_items":  len(news_items),
        "pump_coins":  len(pump_coins),
        "narratives":  narratives,
        "ts":          datetime.now().isoformat(),
    }

    if notify_user_id and bot and narratives:
        top = narratives[0]
        try:
            await bot.send_message(
                chat_id=notify_user_id,
                text=(
                    f"🧠 Intel Update\n\n"
                    f"🔥 Top narrative: {top['narrative']}\n"
                    f"📊 {len(ct_signals)} CT signals | {len(news_items)} news | {len(pump_coins)} new launches\n"
                    f"Use /intel for full report"
                )
            )
        except:
            pass

    return summary
