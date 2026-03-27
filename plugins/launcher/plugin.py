"""Launcher plugin v2.

Features
--------
• Named workspaces defined in config.yaml — launch many apps/URLs at once.
• App aliases   — map short names ("code", "chrome") to real executables.
• Fuzzy matching — "open vscode" still works even though the binary is "code".
• Launch history — every launch is logged to SQLite via core.db so you can
                    see what you opened and when.
• Smart dispatch — URLs always open in browser; absolute paths use the OS
                    file-open verb; everything else tries aliases first, then
                    falls back to direct subprocess / xdg-open / open / start.
• Staggered launch — workspace items open 300 ms apart to avoid race on
                    slow display managers.
• Uses core.db.DB — WAL mode, migrations, no raw sqlite3 calls.

Config (config.yaml)
--------------------

  workspaces:
    dev:
      - code
      - https://github.com
      - ~/projects
    work:
      - chrome
      - https://mail.google.com
      - slack

  app_aliases:
    vscode: code
    browser: google-chrome
    term: gnome-terminal
    editor: nvim
    notes: obsidian

Dispatcher trigger phrases
--------------------------
  open workspace <name>
  list workspaces
  open <target>           (file, URL, or app)
  launch <target>
  launch history
"""

import os
import platform
import subprocess
import time
import re
from plugins.base import PluginBase
from core.config import get
from core.db import DB


# ---------------------------------------------------------------------------
# Default aliases — overridden / extended by config.yaml app_aliases
# ---------------------------------------------------------------------------
_DEFAULT_ALIASES: dict[str, str] = {
    "vscode"   : "code",
    "vs code"  : "code",
    "terminal" : "gnome-terminal",
    "term"     : "gnome-terminal",
    "browser"  : "google-chrome",
    "chrome"   : "google-chrome",
    "firefox"  : "firefox",
    "files"    : "nautilus",
    "finder"   : "open -a Finder",
    "explorer" : "explorer.exe",
    "calc"     : "gnome-calculator",
    "editor"   : "gedit",
    "notes"    : "obsidian",
    "slack"    : "slack",
    "discord"  : "discord",
    "spotify"  : "spotify",
    "gimp"     : "gimp",
    "vlc"      : "vlc",
}

# ---------------------------------------------------------------------------
# DB migration name
# ---------------------------------------------------------------------------
_MIGRATION_HISTORY = "launcher_001_history"


def _system() -> str:
    return platform.system()   # "Linux", "Darwin", "Windows"


# ---------------------------------------------------------------------------
# Core open helper
# ---------------------------------------------------------------------------

def _open_target(target: str, aliases: dict[str, str]) -> str:
    """Open a file, URL, or application. Returns status string."""
    target = target.strip()
    sys    = _system()

    # 1. Resolve alias
    resolved = aliases.get(target.lower(), target)

    # 2. URL
    if resolved.startswith(("http://", "https://", "www.")):
        url = resolved if resolved.startswith("http") else f"https://{resolved}"
        try:
            if sys == "Darwin":
                subprocess.Popen(["open", url])
            elif sys == "Windows":
                os.startfile(url)
            else:
                subprocess.Popen(["xdg-open", url])
            return f"opened browser → {url}"
        except Exception as exc:
            return f"browser open failed: {exc}"

    # 3. File / directory path
    expanded = os.path.expanduser(resolved)
    if os.path.exists(expanded):
        try:
            if sys == "Darwin":
                subprocess.Popen(["open", expanded])
            elif sys == "Windows":
                os.startfile(expanded)
            else:
                subprocess.Popen(["xdg-open", expanded])
            return f"opened path → {expanded}"
        except Exception as exc:
            return f"path open failed: {exc}"

    # 4. Application name / command
    try:
        # Handle "open -a Finder" style resolved values (macOS)
        parts = resolved.split()
        if sys == "Darwin" and len(parts) >= 2 and parts[0] == "open":
            subprocess.Popen(parts)
        elif sys == "Darwin":
            subprocess.Popen(["open", "-a", resolved])
        elif sys == "Windows":
            subprocess.Popen(f'start "" "{resolved}"', shell=True)
        else:
            # Try direct exec first, then xdg-open as fallback
            try:
                subprocess.Popen([resolved])
            except FileNotFoundError:
                subprocess.Popen(["xdg-open", resolved])
        return f"launched → {resolved}"
    except FileNotFoundError:
        return f"not found: {resolved}"
    except Exception as exc:
        return f"launch failed: {exc}"


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class Plugin(PluginBase):
    priority = 8

    def __init__(self):
        self._workspaces: dict = get("workspaces", {}) or {}
        # Merge default aliases with config-defined ones (config wins)
        cfg_aliases = get("app_aliases", {}) or {}
        self._aliases: dict[str, str] = {**_DEFAULT_ALIASES, **{k.lower(): v for k, v in cfg_aliases.items()}}

        # DB for launch history
        self._db = DB()
        self._db.migrate(_MIGRATION_HISTORY, """
            CREATE TABLE IF NOT EXISTS launch_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL    NOT NULL,
                target    TEXT    NOT NULL,
                resolved  TEXT    NOT NULL,
                workspace TEXT    DEFAULT '',
                result    TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_launch_ts     ON launch_history(ts);
            CREATE INDEX IF NOT EXISTS idx_launch_target ON launch_history(target);
        """)

    # ------------------------------------------------------------------ #

    def matches(self, text: str) -> bool:
        t = text.lower()
        if any(kw in t for kw in ("workspace", "switch to", "list workspaces", "launch history", "open workspace")):
            return True
        # Known workspace names
        for name in self._workspaces:
            if name.lower() in t:
                return True
        return False

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(kw in t for kw in ("list workspace", "show workspace", "workspaces")):
            return self._list_workspaces()
        if "launch history" in t or "open history" in t:
            return self._launch_history()
        # Named workspace match
        for name in self._workspaces:
            if name.lower() in t:
                return self._launch_workspace(name)
        return "Workspace not found. Try: list workspaces"

    # ------------------------------------------------------------------ #
    # Public API called by dispatcher
    # ------------------------------------------------------------------ #

    def _launch_workspace(self, name: str) -> str:
        items = self._workspaces.get(name, [])
        if not items:
            return f"Workspace '{name}' is empty or not defined."
        results = []
        for item in items:
            result = _open_target(item, self._aliases)
            self._log(item, result, workspace=name)
            results.append(f"  {item:<30} {result}")
            time.sleep(0.3)
        return f"Workspace '{name}' launched ({len(items)} item{'s' if len(items)!=1 else ''}):\n" + "\n".join(results)

    def _launch_app(self, target: str) -> str:
        """Open a single app/URL/file and log it."""
        result = _open_target(target, self._aliases)
        self._log(target, result)
        return result

    def _list_workspaces(self) -> str:
        if not self._workspaces:
            return (
                "No workspaces defined. Add them to config.yaml:\n\n"
                "  workspaces:\n"
                "    dev:\n"
                "      - code\n"
                "      - https://github.com\n"
                "      - ~/projects\n"
                "    work:\n"
                "      - chrome\n"
                "      - https://mail.google.com\n"
            )
        lines = []
        for name, items in self._workspaces.items():
            lines.append(f"  {name:<16} {', '.join(str(i) for i in items)}")
        return "Workspaces:\n" + "\n".join(lines)

    def _launch_history(self, limit: int = 15) -> str:
        """Show recent launch history from SQLite."""
        rows = self._db.fetchall(
            "SELECT ts, target, result, workspace FROM launch_history "
            "ORDER BY id DESC LIMIT ?", (limit,)
        )
        if not rows:
            return "No launch history yet."
        lines = []
        for r in rows:
            when = time.strftime("%d %b %H:%M", time.localtime(r["ts"]))
            ws   = f" [{r['workspace']}]" if r.get("workspace") else ""
            lines.append(f"  {when}  {r['target']:<24}{ws}  {r['result']}")
        return "Launch history (latest first):\n" + "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _log(self, target: str, result: str, workspace: str = "") -> None:
        """Persist a launch event to launch_history."""
        resolved = self._aliases.get(target.lower(), target)
        try:
            self._db.execute(
                "INSERT INTO launch_history (ts, target, resolved, workspace, result) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), target, resolved, workspace, result)
            )
        except Exception as exc:
            print(f"[launcher] history log failed: {exc}")
