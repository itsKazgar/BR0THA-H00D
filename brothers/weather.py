import requests, sys, os, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import personality
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

NAME        = "Weather Brother"
DESCRIPTION = "Live weather for any city — free, no key needed"
ENABLED     = True
COMMANDS    = ["weather <city>", "weather london", "forecast tokyo"]

TRIGGERS    = ["weather", "forecast", "temperature", "how hot", "how cold",
               "raining", "will it rain", "whats the weather"]

def run(user_input: str):
    lower = user_input.lower().strip()
    if not any(lower.startswith(t) for t in TRIGGERS):
        return None

    # Extract city
    city = lower
    for t in TRIGGERS:
        city = city.replace(t, "").strip()
    city = city.strip("?! ") or "auto"

    try:
        r = requests.get(f"https://wttr.in/{city}?format=4", timeout=6)
        if r.status_code == 200:
            result = f"🌤️  {r.text.strip()}"
            threading.Thread(target=personality.evolve,
                args=("weather", f"checked weather for {city}"), daemon=True).start()
            return result
        return "❌ Could not fetch weather."
    except Exception as e:
        return f"❌ Weather failed: {e}"
