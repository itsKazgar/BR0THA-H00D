import time
from core import brain, ram_router

class BaseAgent:
    def __init__(self, name: str, prefer_tier: str = None):
        self.name        = name
        self.prefer_tier = prefer_tier
        self.model_info  = ram_router.pick_best_model(prefer_tier)
        self.model       = self.model_info.get("selected")
        self.tier        = self.model_info.get("tier")
        self.state       = brain.load_state(name)
        print(f"[{self.name}] online | model={self.model} | tier={self.tier}")

    def remember(self, content: str, type: str = "memory", tags: str = ""):
        brain.remember(self.name, content, type=type, tags=tags)

    def recall(self, limit: int = 10):
        return brain.recall(agent=self.name, limit=limit)

    def recall_all(self, limit: int = 20):
        return brain.recall(limit=limit)

    def share_idea(self, idea: str):
        brain.share_idea(self.name, idea)

    def get_ideas(self):
        return brain.get_ideas()

    def learn(self, topic: str, insight: str):
        brain.learn(self.name, topic, insight)

    def get_learnings(self, topic: str = None):
        return brain.get_learnings(topic=topic)

    def save(self):
        brain.save_state(self.name, self.state)

    def think(self, prompt: str) -> str:
        if self.tier == "free":
            return self._think_ollama(prompt)
        elif self.tier == "api":
            return self._think_api(prompt)
        elif self.tier == "ultra":
            return self._think_cerebras(prompt)
        else:
            return "[no model available — check ram_router]"

    def _think_ollama(self, prompt: str) -> str:
        try:
            import requests
            r = requests.post("http://localhost:11434/api/generate", json={
                "model": self.model, "prompt": prompt, "stream": False
            }, timeout=120)
            return r.json().get("response", "").strip()
        except Exception as e:
            return f"[ollama error: {e}]"

    def _think_api(self, prompt: str) -> str:
        import os
        if "claude" in self.model:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}])
                return msg.content[0].text.strip()
            except Exception as e:
                return f"[claude error: {e}]"
        if "gpt" in self.model:
            try:
                import openai
                client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                r = client.chat.completions.create(model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}])
                return r.choices[0].message.content.strip()
            except Exception as e:
                return f"[openai error: {e}]"
        if "groq" in self.model:
            try:
                import requests
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                    json={"model": "llama3-8b-8192", "messages": [{"role":"user","content":prompt}]},
                    timeout=30)
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                return f"[groq error: {e}]"
        return "[unknown api model]"

    def _think_cerebras(self, prompt: str) -> str:
        try:
            import os, requests
            r = requests.post("https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('CEREBRAS_API_KEY')}"},
                json={"model": "llama3.1-8b", "messages": [{"role":"user","content":prompt}]},
                timeout=30)
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"[cerebras error: {e}]"

    def run(self):
        raise NotImplementedError(f"{self.name}.run() not implemented")

    def run_once(self):
        raise NotImplementedError(f"{self.name}.run_once() not implemented")
