"""Launcher plugin — open apps, files, URLs; launch named workspaces."""

import os
import platform
import subprocess
import time
from plugins.base import PluginBase
from core.config import get

_INTENTS = {
    ("workspace ", "open workspace", "launch workspace", "switch to ") : "_workspace",
    ("list workspace", "show workspace", "workspaces")                  : "_list_workspaces",
    ("open ", "launch ", "start ")                                      : "_open",
}


def _launch(target: str) -> str:
    """Open a file, URL, or application cross-platform."""
    sys = platform.system()
    try:
        if target.startswith(("http://", "https://")):
            # Always use browser for URLs
            if sys == "Darwin":
                subprocess.Popen(["open", target])
            elif sys == "Windows":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
            return f"opening {target}"
        elif os.path.exists(os.path.expanduser(target)):
            path = os.path.expanduser(target)
            if sys == "Darwin":
                subprocess.Popen(["open", path])
            elif sys == "Windows":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
            return f"opening {path}"
        else:
            # Treat as app name
            if sys == "Darwin":
                subprocess.Popen(["open", "-a", target])
            elif sys == "Windows":
                subprocess.Popen(["start", target], shell=True)
            else:
                subprocess.Popen([target])
            return f"launching {target}"
    except FileNotFoundError:
        return f"not found: {target}"
    except Exception as e:
        return f"error: {e}"


class Plugin(PluginBase):
    priority = 8  # just below system, above everything else

    def __init__(self):
        self._workspaces: dict = get("workspaces", {})

    def matches(self, text: str) -> bool:
        t = text.lower()
        # Don't shadow system's 'open' for files — only match known workspace names
        # or explicit workspace commands
        if any(kw in t for kw in ("workspace", "switch to")):
            return True
        if "list workspace" in t or "show workspace" in t:
            return True
        # Match known workspace names directly: "dev", "work", etc.
        for name in self._workspaces:
            if name.lower() in t:
                return True
        return False

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(kw in t for kw in ("list workspace", "show workspace", "workspaces")):
            return self._list_workspaces(text)
        # Detect named workspace
        for name in self._workspaces:
            if name.lower() in t:
                return self._launch_workspace(name)
        return "Workspace not found. Try: list workspaces"

    def _launch_workspace(self, name: str) -> str:
        items = self._workspaces.get(name, [])
        if not items:
            return f"Workspace '{name}' is empty."
        results = []
        for item in items:
            result = _launch(item)
            results.append(f"  {item}  →  {result}")
            time.sleep(0.3)  # slight stagger to avoid race on slow systems
        return f"Workspace '{name}' launched ({len(items)} items):\n" + "\n".join(results)

    def _list_workspaces(self, text: str) -> str:
        if not self._workspaces:
            return (
                "No workspaces defined. Add them to config.yaml:\n\n"
                "  workspaces:\n"
                "    dev:\n"
                "      - code\n"
                "      - https://github.com\n"
                "      - ~/projects\n"
            )
        lines = []
        for name, items in self._workspaces.items():
            lines.append(f"  {name}: {', '.join(items)}")
        return "Workspaces:\n" + "\n".join(lines)
