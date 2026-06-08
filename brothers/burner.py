import os, requests, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import brain, personality
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Burner Brother"
DESCRIPTION = "Disposable emails on demand — generate, check inbox, grab codes"
ENABLED     = True
COMMANDS    = ["burner", "burner email", "check inbox", "new burner", "get code"]

TRIGGERS    = ["burner", "temp email", "disposable email", "fake email",
               "check inbox", "new email", "get code", "check email"]

BASE = "https://api.guerrillamail.com/ajax.php"

def _new_email() -> dict:
    """Generate a fresh burner email address."""
    try:
        r = requests.get(BASE, params={"f": "get_email_address"}, timeout=8)
        d = r.json()
        return {
            "email":    d["email_addr"],
            "token":    d["sid_token"],
            "alias":    d["email_addr"].split("@")[0],
        }
    except Exception as e:
        return {"error": str(e)}

def _check_inbox(token: str) -> list:
    """Check inbox for a given session token."""
    try:
        r = requests.get(BASE, params={"f": "get_email_list", "offset": 0,
                                        "sid_token": token}, timeout=8)
        emails = r.json().get("list", [])
        return emails
    except:
        return []

def _read_email(token: str, mail_id: str) -> str:
    """Read full email content."""
    try:
        r = requests.get(BASE, params={"f": "fetch_email", "email_id": mail_id,
                                        "sid_token": token}, timeout=8)
        return r.json().get("mail_body", "")
    except:
        return ""

def _extract_code(text: str) -> str:
    """Try to find a verification code in email body."""
    import re
    # Look for 4-8 digit codes
    codes = re.findall(r'\b\d{4,8}\b', text)
    return codes[0] if codes else None

def _get_active() -> dict:
    """Load the current active burner from brain."""
    return brain.load_state("burner_active") or {}

def _save_active(data: dict):
    brain.save_state("burner_active", data)

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    # CHECK INBOX
    if any(x in lower for x in ["check inbox", "check email", "any emails", "got mail"]):
        active = _get_active()
        if not active:
            return "❌ No active burner. Say 'burner email' to generate one."
        msgs = _check_inbox(active["token"])
        if not msgs:
            return f"📭 Inbox empty for {active['email']}"
        lines = [f"📬 Inbox for {active['email']}\n"]
        for m in msgs[:5]:
            lines.append(f"  • From: {m.get('mail_from','?')}")
            lines.append(f"    Subject: {m.get('mail_subject','?')}")
            lines.append(f"    ID: {m.get('mail_id','?')}")
        return "\n".join(lines)

    # GET CODE — read latest email and extract verification code
    if any(x in lower for x in ["get code", "verification code", "otp", "code"]):
        active = _get_active()
        if not active:
            return "❌ No active burner. Say 'burner email' first."
        msgs = _check_inbox(active["token"])
        if not msgs:
            return f"📭 No emails yet at {active['email']}"
        # Read the latest
        latest = msgs[0]
        body = _read_email(active["token"], latest["mail_id"])
        code = _extract_code(body)
        if code:
            return f"🔑 Code found: {code}\n  From: {latest.get('mail_from','?')}\n  Subject: {latest.get('mail_subject','?')}"
        return f"📧 No code found in latest email.\n  Subject: {latest.get('mail_subject','?')}\n  Preview: {body[:200]}"

    # NEW BURNER / GENERATE
    data = _new_email()
    if "error" in data:
        return f"❌ Could not generate burner: {data['error']}"

    _save_active(data)
    brain.remember("burner", f"Generated burner: {data['email']}", type="burner")

    threading.Thread(target=personality.evolve,
        args=("burner", f"generated burner email {data['email']}"), daemon=True).start()

    return (f"🔥 BURNER READY\n"
            f"  📧 Email: {data['email']}\n"
            f"  📥 Say 'check inbox' to check for messages\n"
            f"  🔑 Say 'get code' to extract verification codes\n"
            f"  ⚠️  Expires after ~1 hour of inactivity")
