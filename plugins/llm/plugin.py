"""LLM plugin — fallback brain, supports all OpenAI-compatible backends."""

import json
import urllib.request
import urllib.error
from plugins.base import PluginBase
from core.config import get_llm_config


class Plugin(PluginBase):
    priority = 999  # last resort fallback

    def __init__(self):
        self._reload()

    def _reload(self):
        cfg = get_llm_config()
        self._base_url = cfg.get("base_url", "http://localhost:1234/v1").rstrip("/")
        self._api_key  = cfg.get("api_key", "lm-studio")
        self._model    = cfg.get("model", "local-model")
        self._max_tok  = cfg.get("max_tokens", 512)
        self._temp     = cfg.get("temperature", 0.7)
        self._sysprompt = cfg.get("system_prompt", "You are Jarvis, a concise AI assistant.")
        self._mode     = cfg.get("_mode", "unknown")
        print(f"[llm] mode={self._mode}  model={self._model}  url={self._base_url}")

    def matches(self, text: str) -> bool:
        return True

    def run(self, text: str, memory) -> str:
        messages = [{"role": "system", "content": self._sysprompt}]
        for entry in memory.last(10):
            messages.append({"role": entry["role"], "content": entry["content"]})

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tok,
            "temperature": self._temp,
        }).encode()

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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return f"[LLM {self._mode} error {e.code}]: {body[:300]}"
        except urllib.error.URLError as e:
            if "Connection refused" in str(e):
                return (
                    f"[LLM] Cannot reach {self._mode} at {self._base_url}.\n"
                    f"Is LM Studio / Ollama running? Check config.yaml llm_mode."
                )
            return f"[LLM network error]: {e}"
        except Exception as e:
            return f"[LLM error]: {e}"
