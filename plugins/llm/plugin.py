"""LLM plugin — fallback conversational brain, streaming-aware, context-aware."""

import json
import urllib.request
import urllib.error
from plugins.base import PluginBase
from core.config import get_llm_config


class Plugin(PluginBase):
    priority = 999  # always last resort

    def __init__(self):
        self._reload()

    def _reload(self):
        cfg = get_llm_config()
        self._base_url  = cfg.get("base_url", "http://localhost:1234/v1").rstrip("/")
        self._api_key   = cfg.get("api_key",   "lm-studio")
        self._model     = cfg.get("model",     "local-model")
        self._max_tok   = cfg.get("max_tokens",  1024)
        self._temp      = cfg.get("temperature",  0.7)
        self._sysprompt = cfg.get(
            "system_prompt",
            (
                "You are Jarvis, a highly capable AI assistant inspired by Iron Man's JARVIS.\n"
                "Be concise, precise, and practical. Answer in plain text unless the user asks for code.\n"
                "For code, use fenced code blocks with the language tag.\n"
                "Never refuse reasonable requests. Get straight to the point."
            )
        )
        self._mode = cfg.get("_mode", "unknown")
        print(f"[llm] mode={self._mode}  model={self._model}  url={self._base_url}")

    def matches(self, text: str) -> bool:
        return True  # catch-all

    def run(self, text: str, memory) -> str:
        messages = [{"role": "system", "content": self._sysprompt}]

        # Include last N turns for context
        for entry in memory.last(12):
            messages.append({"role": entry["role"], "content": entry["content"]})

        # Add current user turn if not already in memory
        if not messages or messages[-1].get("role") != "user":
            messages.append({"role": "user", "content": text})

        payload = json.dumps({
            "model"       : self._model,
            "messages"    : messages,
            "max_tokens"  : self._max_tok,
            "temperature" : self._temp,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type" : "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return f"[LLM {self._mode} error {e.code}]: {body[:400]}"
        except urllib.error.URLError as e:
            if "Connection refused" in str(e):
                return (
                    f"[LLM] Cannot reach {self._mode} at {self._base_url}.\n"
                    "Is LM Studio / Ollama running?  Check config.yaml llm_mode."
                )
            return f"[LLM network error]: {e}"
        except Exception as e:
            return f"[LLM error]: {e}"
