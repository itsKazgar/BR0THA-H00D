"""
ASSISTANT TOOLS — plugs into assistant.py
Web search, scraping, email, SMS, content, automation, personal tracking
"""
import os, sys, json, time, requests, re
from datetime import datetime
from urllib.parse import quote
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, llm

CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'
BD='\033[1m';  DM='\033[2m';  RS='\033[0m';  MG='\033[95m'

# ═══════════════════════════════════════════════════════════
#  WEB SEARCH
# ═══════════════════════════════════════════════════════════

def web_search(query: str, limit=5) -> str:
    """Search via Groq LLM knowledge."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return "No search API configured. Add GROQ_API_KEY to .env"
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 800,
                "temperature": 0.3,
                "messages": [{
                    "role": "user",
                    "content": (f"Search query: {query}\n\n"
                               "Give a concise, factual answer with key facts. "
                               "Use 3-5 bullet points. Be specific and useful. No fluff.")
                }]
            }, timeout=15)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return f"Search failed: {r.status_code}"
    except Exception as e:
        return f"Search failed: {e}"


def web_search_html(query: str, limit=5) -> str:
    """Fallback HTML search scraper."""
    try:
        url  = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        r    = requests.get(url, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
        text = r.text
        # Extract result snippets
        snippets = re.findall(r'class="result__snippet">(.*?)</a>', text)
        titles   = re.findall(r'class="result__title">\s*<a[^>]*>(.*?)</a>', text)
        links    = re.findall(r'class="result__url">(.*?)</span>', text)
        results  = []
        for i in range(min(limit, len(snippets))):
            title   = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ""
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            link    = links[i].strip() if i < len(links) else ""
            if title:
                results.append(f"🔗 {title}")
            if snippet:
                results.append(f"   {snippet[:200]}")
            if link:
                results.append(f"   {link}")
            results.append("")
        return "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search failed: {e}"


# ═══════════════════════════════════════════════════════════
#  WEB SCRAPER
# ═══════════════════════════════════════════════════════════

def scrape_url(url: str, summarize=True) -> str:
    """Fetch a URL and return clean text content."""
    try:
        r = requests.get(url, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        text = r.text

        # Strip HTML tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>',  '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        text = text[:4000]  # cap at 4000 chars

        if summarize and len(text) > 500:
            prompt = f"Summarize this web page content in 3-5 bullet points:\n\n{text}"
            summary, _ = llm.think(prompt)
            return summary if summary else text[:1000]

        return text

    except Exception as e:
        return f"Could not scrape {url}: {e}"


def scrape_price(url: str, selector_hint="price") -> str:
    """Try to extract a price from a product page."""
    try:
        r    = requests.get(url, timeout=12,
                            headers={"User-Agent": "Mozilla/5.0"})
        text = r.text
        # Look for price patterns
        prices = re.findall(r'\$[\d,]+\.?\d*', text)
        if prices:
            return f"Prices found on page: {', '.join(list(set(prices))[:5])}"
        return "No prices found on page."
    except Exception as e:
        return f"Could not check price: {e}"


# ═══════════════════════════════════════════════════════════
#  EMAIL SENDER
# ═══════════════════════════════════════════════════════════

def send_email(to: str, subject: str, body: str) -> str:
    """Send email via SMTP. Configure SMTP_* in .env"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        return ("❌ Email not configured. Add to .env:\n"
                "  SMTP_HOST=smtp.gmail.com\n"
                "  SMTP_PORT=587\n"
                "  SMTP_USER=your@gmail.com\n"
                "  SMTP_PASS=your_app_password\n"
                "  SMTP_FROM=your@gmail.com\n"
                "  (Gmail: use App Password, not your real password)")

    try:
        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        brain.remember("assistant",
            f"EMAIL SENT to={to} subject={subject[:50]}",
            type="email_sent", tags="email,sent")
        return f"✅ Email sent to {to}"

    except Exception as e:
        return f"❌ Email failed: {e}"


def mass_email(recipients: list, subject: str, body_template: str,
               personalize=True) -> str:
    """Send personalized emails to a list of recipients."""
    results = []
    for r in recipients:
        if isinstance(r, dict):
            name  = r.get("name", "")
            email = r.get("email", "")
        else:
            name  = ""
            email = str(r)

        body = body_template
        if personalize and name:
            body = body.replace("{name}", name).replace("{Name}", name)

        result = send_email(email, subject, body)
        results.append(f"  {email}: {result}")
        time.sleep(0.5)  # be polite to SMTP server

    return f"Mass email done ({len(recipients)} recipients):\n" + "\n".join(results)


# ═══════════════════════════════════════════════════════════
#  SMS (Twilio)
# ═══════════════════════════════════════════════════════════

def send_sms(to: str, message: str) -> str:
    """Send SMS via Twilio. Configure TWILIO_* in .env"""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM", "")

    if not all([account_sid, auth_token, from_number]):
        return ("❌ SMS not configured. Add to .env:\n"
                "  TWILIO_ACCOUNT_SID=your_sid\n"
                "  TWILIO_AUTH_TOKEN=your_token\n"
                "  TWILIO_FROM=+1234567890\n"
                "  Sign up free at twilio.com (free trial credits included)")

    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            auth=(account_sid, auth_token),
            data={"From": from_number, "To": to, "Body": message},
            timeout=10)
        if r.status_code == 201:
            brain.remember("assistant",
                f"SMS SENT to={to} msg={message[:50]}",
                type="sms_sent", tags="sms,sent")
            return f"✅ SMS sent to {to}"
        return f"❌ SMS failed: {r.json().get('message', r.text)}"
    except Exception as e:
        return f"❌ SMS failed: {e}"


# ═══════════════════════════════════════════════════════════
#  CONTENT CREATION
# ═══════════════════════════════════════════════════════════

def create_document(title: str, content: str, fmt="txt") -> str:
    """Save a document to the assistant_docs folder."""
    docs_dir = os.path.join(os.path.dirname(__file__), "../assistant_docs")
    os.makedirs(docs_dir, exist_ok=True)
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    filename   = f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M')}.{fmt}"
    filepath   = os.path.join(docs_dir, filename)
    with open(filepath, 'w') as f:
        f.write(content)
    brain.remember("assistant",
        f"DOCUMENT CREATED: {filename}",
        type="document", tags="document,created")
    return f"✅ Saved: {filepath}"


def generate_invoice(client: str, items: list, notes="") -> str:
    """Generate a plain text invoice."""
    now      = datetime.now()
    inv_num  = f"INV-{now.strftime('%Y%m%d%H%M')}"
    total    = sum(item.get("amount", 0) for item in items)
    lines    = [
        f"INVOICE {inv_num}",
        f"Date: {now.strftime('%B %d, %Y')}",
        f"Bill To: {client}",
        "=" * 40,
    ]
    for item in items:
        lines.append(f"  {item.get('desc','Item'):<25} ${item.get('amount',0):>8.2f}")
    lines += ["=" * 40, f"  {'TOTAL':<25} ${total:>8.2f}", ""]
    if notes:
        lines += [f"Notes: {notes}", ""]
    content = "\n".join(lines)
    return create_document(f"Invoice_{client}", content)


def write_social_post(topic: str, platform="twitter") -> str:
    """Generate a social media post."""
    limits = {"twitter": 280, "linkedin": 3000, "instagram": 2200}
    limit  = limits.get(platform.lower(), 280)
    prompt = (f"Write a {platform} post about: {topic}\n"
              f"Max {limit} characters. Be engaging and natural. "
              f"Include relevant hashtags at the end.")
    resp, _ = llm.think(prompt)
    return resp if resp else "Could not generate post."


# ═══════════════════════════════════════════════════════════
#  PERSONAL TRACKER
# ═══════════════════════════════════════════════════════════

def log_expense(amount: float, category: str, note="") -> str:
    """Log an expense to brain."""
    entry = {
        "amount":   amount,
        "category": category,
        "note":     note,
        "date":     datetime.now().isoformat(),
    }
    brain.remember("assistant",
        f"EXPENSE ${amount:.2f} | {category} | {note}",
        type="expense", tags=f"expense,{category.lower()}")
    return f"✅ Logged: ${amount:.2f} — {category}"


def get_expenses(days=30) -> str:
    """Show expense summary."""
    expenses = brain.recall(type="expense", limit=100)
    if not expenses:
        return "No expenses logged yet. Use: expense 25.50 food lunch"
    total    = 0
    by_cat   = {}
    for e in expenses:
        c = e["content"]
        try:
            amt  = float(re.search(r'\$([0-9.]+)', c).group(1))
            cat  = c.split("|")[1].strip()
            total += amt
            by_cat[cat] = by_cat.get(cat, 0) + amt
        except:
            continue
    lines = [f"💰 Total spent: ${total:.2f}", "By category:"]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat:<20} ${amt:.2f}")
    return "\n".join(lines)


def log_habit(habit: str, done=True) -> str:
    """Log a habit completion."""
    status = "✅ done" if done else "❌ skipped"
    brain.remember("assistant",
        f"HABIT {status}: {habit}",
        type="habit", tags=f"habit,{habit.lower()}")
    return f"{status} — {habit} logged for today"


def get_habits(days=7) -> str:
    """Show habit streaks."""
    habits = brain.recall(type="habit", limit=100)
    if not habits:
        return "No habits tracked yet. Use: habit meditation"
    by_habit = {}
    for h in habits:
        c    = h["content"]
        name = c.split(":")[-1].strip()
        done = "✅" in c
        if name not in by_habit:
            by_habit[name] = {"done": 0, "total": 0}
        by_habit[name]["total"] += 1
        if done:
            by_habit[name]["done"] += 1
    lines = ["📊 Habit tracker:"]
    for name, data in by_habit.items():
        pct = data["done"] / data["total"] * 100
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        lines.append(f"  {name:<20} {bar} {pct:.0f}%")
    return "\n".join(lines)


def add_journal(entry: str) -> str:
    """Add a journal entry."""
    brain.remember("assistant",
        f"JOURNAL: {entry}",
        type="journal", tags="journal,personal")
    return f"✅ Journal entry saved."


def get_journal(limit=5) -> str:
    """Show recent journal entries."""
    entries = brain.recall(type="journal", limit=limit)
    if not entries:
        return "No journal entries yet."
    lines = ["📔 Recent journal entries:"]
    for e in entries:
        ts   = e.get("ts", "")[:16]
        text = e["content"].replace("JOURNAL: ", "")
        lines.append(f"\n  [{ts}]\n  {text}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  WEBSITE MONITOR
# ═══════════════════════════════════════════════════════════

def monitor_add(url: str, keyword="") -> str:
    """Add a URL to monitor for changes."""
    brain.remember("assistant",
        f"MONITOR: {url} | keyword={keyword}",
        type="monitor", tags="monitor,watch")
    return f"✅ Now monitoring: {url}"


def monitor_check() -> str:
    """Check all monitored URLs for changes."""
    monitors = brain.recall(type="monitor", limit=20)
    if not monitors:
        return "No URLs being monitored."
    results = []
    for m in monitors:
        url     = m["content"].split("|")[0].replace("MONITOR:", "").strip()
        keyword = m["content"].split("keyword=")[-1].strip() if "keyword=" in m["content"] else ""
        try:
            r    = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r'<[^>]+>', ' ', r.text)
            if keyword and keyword.lower() in text.lower():
                results.append(f"🔔 {url} — keyword '{keyword}' FOUND")
            else:
                results.append(f"✅ {url} — {'no keyword match' if keyword else 'reachable'}")
        except Exception as e:
            results.append(f"❌ {url} — error: {e}")
        time.sleep(0.5)
    return "\n".join(results)


# ═══════════════════════════════════════════════════════════
#  COMMAND ROUTER — called from assistant.py
# ═══════════════════════════════════════════════════════════

def handle_tool_command(inp: str) -> str | None:
    """
    Returns a response if this is a tool command, None otherwise.
    Called from assistant.py handle_special_commands.
    """
    lower = inp.lower().strip()

    # ── Search ─────────────────────────────────────────────
    if lower.startswith("search ") or lower.startswith("google ") or lower.startswith("find "):
        query = re.split(r'^(search|google|find)\s+', inp, flags=re.IGNORECASE)[2]
        return f"🔍 Searching: {query}\n\n" + web_search(query)

    # ── Scrape ─────────────────────────────────────────────
    if lower.startswith("scrape ") or lower.startswith("read url "):
        url = inp.split(" ", 1)[1].strip()
        return f"🌐 Reading {url}...\n\n" + scrape_url(url)

    if lower.startswith("price check ") or lower.startswith("check price "):
        url = re.split(r'price check|check price', inp, flags=re.IGNORECASE)[1].strip()
        return scrape_price(url)

    # ── Email ───────────────────────────────────────────────
    if lower.startswith("email "):
        # email to@addr.com subject | body
        parts = inp[6:].strip()
        try:
            to_part, rest = parts.split(" ", 1)
            if "|" in rest:
                subject, body = rest.split("|", 1)
            else:
                subject = "Message from BR0THER"
                body    = rest
            return send_email(to_part.strip(), subject.strip(), body.strip())
        except:
            return "Usage: email to@addr.com Subject line | Email body"

    # ── SMS ─────────────────────────────────────────────────
    if lower.startswith("sms ") or lower.startswith("text "):
        parts = inp.split(" ", 2)
        if len(parts) >= 3:
            return send_sms(parts[1], parts[2])
        return "Usage: sms +1234567890 Your message here"

    # ── Documents ───────────────────────────────────────────
    if lower.startswith("write ") or lower.startswith("create doc "):
        title   = inp.split(" ", 2)[1] if lower.startswith("write ") else inp.split(" ", 2)[2]
        prompt  = f"Write a complete, well-structured document titled: {inp.split(' ',1)[1]}"
        content, _ = llm.think(prompt)
        return create_document(title, content or "No content generated.")

    if lower.startswith("invoice "):
        # invoice ClientName item1:price item2:price
        parts  = inp.split(" ")[1:]
        client = parts[0] if parts else "Client"
        items  = []
        for p in parts[1:]:
            if ":" in p:
                desc, amt = p.split(":", 1)
                try:
                    items.append({"desc": desc, "amount": float(amt)})
                except:
                    pass
        if not items:
            items = [{"desc": "Services", "amount": 0}]
        return generate_invoice(client, items)

    if lower.startswith("post ") or lower.startswith("tweet "):
        platform = "twitter" if lower.startswith("tweet") else "social media"
        topic    = inp.split(" ", 1)[1]
        return write_social_post(topic, platform)

    # ── Expenses ────────────────────────────────────────────
    if lower.startswith("expense "):
        parts = inp.split(" ", 3)
        try:
            amount   = float(parts[1])
            category = parts[2] if len(parts) > 2 else "general"
            note     = parts[3] if len(parts) > 3 else ""
            return log_expense(amount, category, note)
        except:
            return "Usage: expense 25.50 food lunch with friends"

    if lower in ["expenses", "spending", "my expenses"]:
        return get_expenses()

    # ── Habits ──────────────────────────────────────────────
    if lower.startswith("habit "):
        habit = inp.split(" ", 1)[1]
        done  = "skip" not in lower and "missed" not in lower
        return log_habit(habit, done)

    if lower in ["habits", "my habits", "streak", "streaks"]:
        return get_habits()

    # ── Journal ─────────────────────────────────────────────
    if lower.startswith("journal "):
        entry = inp.split(" ", 1)[1]
        return add_journal(entry)

    if lower in ["journal", "my journal", "diary"]:
        return get_journal()

    # ── Monitor ─────────────────────────────────────────────
    if lower.startswith("monitor ") or lower.startswith("watch url "):
        url = inp.split(" ", 1)[1]
        return monitor_add(url)

    if lower in ["check monitors", "monitors", "check watched"]:
        return monitor_check()

    return None  # not a tool command
