# plugins/clipboard_history/plugin.py
"""
Clipboard History plugin — keeps a session-scoped ring of the last N clipboard
entries and lets you recall, search, or re-copy any of them.

Triggers:
  'clipboard history'          → list recent entries
  'clipboard history 5'        → list last 5
  'clipboard search <keyword>' → search history
  'copy history item 3'        → push item #3 back to clipboard
  'clear clipboard history'    → wipe the history

Depends on: pyperclip (already in requirements.txt via clipboard plugin)
"""
import re
from collections import deque
from plugins.base import PluginBase

_MAX_HISTORY = 50
_history: deque = deque(maxlen=_MAX_HISTORY)  # module-level session store


class Plugin(PluginBase):
    priority = 45  # runs before the plain clipboard plugin (priority 100)

    _triggers = (
        "clipboard history",
        "clipboard search",
        "copy history",
        "clear clipboard history",
        "paste history",
    )

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in self._triggers)

    def run(self, text: str, memory) -> str:
        try:
            import pyperclip
            t = text.lower()

            # Snapshot current clipboard into history on every run
            self._snapshot(pyperclip)

            if "clear" in t:
                _history.clear()
                return "Clipboard history cleared."

            if "search" in t:
                m = re.search(r"search\s+(.+)", t)
                keyword = m.group(1).strip() if m else ""
                return self._search(keyword)

            if re.search(r"copy.+item\s+(\d+)|paste.+item\s+(\d+)|history item\s+(\d+)", t):
                nums = re.findall(r"\d+", t)
                idx = int(nums[-1]) - 1  # 1-based display
                return self._recopy(pyperclip, idx)

            # Default: list history
            m = re.search(r"history\s+(\d+)", t)
            limit = int(m.group(1)) if m else 10
            return self._list(limit)

        except Exception as e:
            return f"[clipboard_history] error: {e}"

    # ------------------------------------------------------------------ #

    def _snapshot(self, pyperclip) -> None:
        """Add current clipboard to history if it's a new entry."""
        try:
            current = pyperclip.paste()
            if current and (not _history or _history[-1] != current):
                _history.append(current)
        except Exception:
            pass

    def _list(self, limit: int) -> str:
        items = list(_history)[-limit:][::-1]  # newest first
        if not items:
            return "Clipboard history is empty."
        lines = [f"{i+1}. {self._truncate(item)}" for i, item in enumerate(items)]
        return "Recent clipboard entries:\n" + "\n".join(lines)

    def _search(self, keyword: str) -> str:
        if not keyword:
            return "Please provide a search keyword."
        matches = [
            (i + 1, item)
            for i, item in enumerate(reversed(list(_history)))
            if keyword.lower() in item.lower()
        ]
        if not matches:
            return f"No clipboard history matches '{keyword}'."
        lines = [f"{idx}. {self._truncate(item)}" for idx, item in matches[:10]]
        return f"Clipboard history matching '{keyword}':\n" + "\n".join(lines)

    def _recopy(self, pyperclip, idx: int) -> str:
        items = list(reversed(list(_history)))
        if idx < 0 or idx >= len(items):
            return f"[clipboard_history] Item #{idx + 1} not found (history has {len(items)} entries)."
        content = items[idx]
        pyperclip.copy(content)
        return f"Copied history item #{idx + 1} to clipboard: {self._truncate(content)}"

    @staticmethod
    def _truncate(s: str, max_len: int = 80) -> str:
        s = s.replace("\n", "↵").replace("\t", "→")
        return s[:max_len] + "…" if len(s) > max_len else s
