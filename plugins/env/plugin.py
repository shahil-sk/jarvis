# plugins/env/plugin.py
"""
Environment Variables plugin — list, get, set, unset, and search
environment variables for the current process.

Triggers:
  'list env'                   → show all env vars (paginated)
  'env PATH' / 'get env HOME'  → get a specific var
  'set env MY_VAR=hello'       → set for this session
  'unset env MY_VAR'           → remove for this session
  'search env proxy'           → search vars by keyword

Note: set/unset only affects the running Jarvis process (os.environ),
not the parent shell. This is by design — shells don't inherit child env changes.
"""
import os
import re
from plugins.base import PluginBase


class Plugin(PluginBase):
    priority = 60

    _triggers = ("env ", " env", "environment variable", "$PATH", "$HOME", "$USER")

    def matches(self, text: str) -> bool:
        t = text.lower()
        return (
            "env" in t.split()
            or "environment variable" in t
            or any(kw in text for kw in ("$PATH", "$HOME", "$USER", "$SHELL"))
        )

    def run(self, text: str, memory) -> str:
        try:
            t = text.lower()

            # set env VAR=value
            m = re.search(r"set\s+env\s+(\w+)[=\s]+(.+)", text, re.IGNORECASE)
            if m:
                return self._set(m.group(1), m.group(2).strip())

            # unset env VAR
            m = re.search(r"unset\s+env\s+(\w+)", text, re.IGNORECASE)
            if m:
                return self._unset(m.group(1))

            # search env keyword
            m = re.search(r"search\s+env\s+(\S+)", text, re.IGNORECASE)
            if m:
                return self._search(m.group(1))

            # get specific var: 'env PATH' or 'get env HOME' or '$PATH'
            dollar = re.search(r"\$(\w+)", text)
            if dollar:
                return self._get(dollar.group(1))

            m = re.search(
                r"(?:get\s+)?env\s+(\w+)|value\s+of\s+(\w+)", text, re.IGNORECASE
            )
            if m:
                var = m.group(1) or m.group(2)
                return self._get(var)

            # list all
            return self._list()
        except Exception as e:
            return f"[env] error: {e}"

    # ------------------------------------------------------------------ #

    def _get(self, var: str) -> str:
        # try exact, then uppercase
        val = os.environ.get(var) or os.environ.get(var.upper())
        if val is None:
            return f"Environment variable '{var}' is not set."
        return f"{var.upper()} = {val}"

    def _set(self, var: str, value: str) -> str:
        os.environ[var.upper()] = value
        return f"Set {var.upper()} = {value} (current session only)."

    def _unset(self, var: str) -> str:
        key = var.upper()
        if key not in os.environ:
            return f"'{key}' is not set."
        del os.environ[key]
        return f"Unset {key}."

    def _search(self, keyword: str) -> str:
        kw = keyword.upper()
        matches = [
            (k, v) for k, v in os.environ.items() if kw in k or kw in v.upper()
        ]
        if not matches:
            return f"No environment variables match '{keyword}'."
        lines = [f"{k} = {v[:80]}{'…' if len(v)>80 else ''}" for k, v in matches[:20]]
        return f"Environment variables matching '{keyword}':\n" + "\n".join(lines)

    def _list(self) -> str:
        items = sorted(os.environ.items())
        lines = [f"{k} = {v[:60]}{'…' if len(v)>60 else ''}" for k, v in items[:30]]
        suffix = f"\n  … and {len(items) - 30} more (use 'search env <keyword>' to filter)." if len(items) > 30 else ""
        return "Environment variables (first 30):\n" + "\n".join(lines) + suffix
