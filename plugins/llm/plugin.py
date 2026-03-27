"""LLM plugin — fallback brain using any OpenAI-compatible API."""

import os
import json
import urllib.request
import urllib.error
from plugins.base import PluginBase
from core.config import get


class Plugin(PluginBase):
    """
    Catches anything no other plugin handles.
    Sends full session memory as context to the LLM.
    Config via config.yaml [jarvis.llm] or env vars.
    """

    # Lowest priority — always matches as last resort
    priority = 999

    def __init__(self):
        cfg = get("llm", {})
        self._base_url = (
            os.environ.get("JARVIS_LLM_URL")
            or cfg.get("base_url", "https://api.openai.com/v1")
        ).rstrip("/")
        self._api_key = (
            os.environ.get("JARVIS_LLM_API_KEY")
            or cfg.get("api_key", "")
        )
        self._model = (
            os.environ.get("JARVIS_LLM_MODEL")
            or cfg.get("model", "gpt-4o-mini")
        )
        self._max_tokens = cfg.get("max_tokens", 512)
        self._temperature = cfg.get("temperature", 0.7)
        self._system_prompt = cfg.get(
            "system_prompt",
            "You are Jarvis, a fast and helpful AI assistant. "
            "Be concise. Avoid unnecessary filler."
        )

    def matches(self, text: str) -> bool:
        return True  # fallback — always matches

    def run(self, text: str, memory) -> str:
        messages = [{"role": "system", "content": self._system_prompt}]
        for entry in memory.last(10):
            messages.append({"role": entry["role"], "content": entry["content"]})

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return f"[LLM error {e.code}] {body[:200]}"
        except Exception as e:
            return f"[LLM error] {e}"
