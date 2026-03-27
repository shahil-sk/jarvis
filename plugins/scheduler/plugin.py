"""Scheduler plugin — reminders + repeating jobs, SQLite-backed, background thread."""

import time
import threading
import sqlite3
import os
import re
from plugins.base import PluginBase
from core.config import get

_DB_PATH = os.path.expanduser("~/.jarvis/memory.db")

# ── DB setup ────────────────────────────────────────────────────────

def _db():
    return sqlite3.connect(get("memory", {}).get("db_path", _DB_PATH))


def _init_scheduler_db():
    con = _db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            fire_at  REAL NOT NULL,       -- unix timestamp
            message  TEXT NOT NULL,
            repeat   TEXT DEFAULT '',     -- '' | 'minutely' | 'hourly' | 'daily'
            done     INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()


# ── time parsing ────────────────────────────────────────────────────────

_UNITS = {
    "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
}


def _parse_delay(text: str):
    """
    Parse 'in X unit' patterns. Returns seconds as int or None.
    Examples: 'in 5 minutes', 'in 2 hours', 'in 30 seconds'
    """
    m = re.search(r"in\s+(\d+)\s+(\w+)", text.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2).rstrip("s") + ("s" if m.group(2).endswith("s") else "")
        # normalise
        unit = m.group(2).lower()
        mult = _UNITS.get(unit)
        if mult:
            return n * mult
    return None


def _parse_repeat(text: str) -> str:
    t = text.lower()
    if "every minute" in t or "minutely" in t:
        return "minutely"
    if "every hour" in t or "hourly" in t:
        return "hourly"
    if "every day" in t or "daily" in t:
        return "daily"
    return ""


def _extract_message(text: str) -> str:
    """Strip scheduling keywords, return the reminder message."""
    text = re.sub(r"remind(\s+me)?\s+(in\s+\d+\s+\w+\s+)?(to\s+)?", "", text, flags=re.I)
    text = re.sub(r"(in\s+\d+\s+\w+)", "", text, flags=re.I)
    text = re.sub(r"(every\s+\w+)", "", text, flags=re.I)
    text = re.sub(r"(scheduler?|reminder|schedule)", "", text, flags=re.I)
    return text.strip(" ,.:")


# ── background ticker ────────────────────────────────────────────────────

def _fire_notification(message: str):
    import platform, subprocess
    sys = platform.system()
    try:
        if sys == "Darwin":
            subprocess.run(["osascript", "-e",
                f'display notification "{message}" with title "Jarvis Reminder"'])
        elif sys == "Windows":
            pass  # toast handled via PowerShell if needed
        else:
            subprocess.run(["notify-send", "Jarvis Reminder", message])
    except Exception:
        pass
    print(f"\n\033[93m[Reminder] {message}\033[0m\nYou: ", end="", flush=True)


def _ticker(db_path: str):
    """Runs in a daemon thread. Polls DB every 5s, fires due reminders."""
    while True:
        try:
            con = sqlite3.connect(db_path)
            now = time.time()
            due = con.execute(
                "SELECT id, message, repeat FROM reminders WHERE fire_at<=? AND done=0",
                (now,)
            ).fetchall()
            for rid, msg, repeat in due:
                _fire_notification(msg)
                if repeat:
                    intervals = {"minutely": 60, "hourly": 3600, "daily": 86400}
                    next_fire = now + intervals.get(repeat, 86400)
                    con.execute("UPDATE reminders SET fire_at=? WHERE id=?", (next_fire, rid))
                else:
                    con.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
            con.commit()
            con.close()
        except Exception:
            pass
        time.sleep(5)


_ticker_started = False


def _ensure_ticker(db_path: str):
    global _ticker_started
    if not _ticker_started:
        t = threading.Thread(target=_ticker, args=(db_path,), daemon=True)
        t.start()
        _ticker_started = True


# ── Plugin ──────────────────────────────────────────────────────────────────

class Plugin(PluginBase):
    priority = 22

    def __init__(self):
        self._db_path = os.path.expanduser(
            get("memory", {}).get("db_path", _DB_PATH)
        )
        _init_scheduler_db()
        _ensure_ticker(self._db_path)

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in (
            "remind me", "reminder", "schedule",
            "in 5 min", "in 10 min", "in 1 hour",
            "list reminders", "show reminders",
            "cancel reminder", "delete reminder",
        )) or bool(re.search(r"remind.+in\s+\d+", t))

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(kw in t for kw in ("list reminder", "show reminder")):
            return self._list()
        if any(kw in t for kw in ("cancel reminder", "delete reminder")):
            return self._cancel(text)
        return self._add(text)

    def _add(self, text: str) -> str:
        delay = _parse_delay(text)
        if delay is None:
            return (
                "Could not parse time. Examples:\n"
                "  remind me in 10 minutes to call John\n"
                "  remind me in 2 hours check build\n"
                "  schedule daily remind me to drink water"
            )
        message = _extract_message(text) or "Reminder!"
        repeat  = _parse_repeat(text)
        fire_at = time.time() + delay
        con = sqlite3.connect(self._db_path)
        cur = con.execute(
            "INSERT INTO reminders (fire_at, message, repeat) VALUES (?, ?, ?)",
            (fire_at, message, repeat)
        )
        rid = cur.lastrowid
        con.commit()
        con.close()
        when = time.strftime("%H:%M:%S", time.localtime(fire_at))
        rep  = f"  repeats {repeat}" if repeat else ""
        return f"Reminder #{rid} set for {when}{rep}: {message}"

    def _list(self) -> str:
        con = sqlite3.connect(self._db_path)
        rows = con.execute(
            "SELECT id, fire_at, message, repeat FROM reminders WHERE done=0 ORDER BY fire_at"
        ).fetchall()
        con.close()
        if not rows:
            return "No pending reminders."
        lines = []
        for rid, fa, msg, rep in rows:
            when = time.strftime("%d %b %H:%M", time.localtime(fa))
            rep_str = f" [{rep}]" if rep else ""
            lines.append(f"#{rid}  {when}{rep_str}  {msg}")
        return "\n".join(lines)

    def _cancel(self, text: str) -> str:
        m = re.search(r"(\d+)", text)
        if not m:
            return "Usage: cancel reminder <id>"
        rid = int(m.group(1))
        con = sqlite3.connect(self._db_path)
        con.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
        con.commit()
        con.close()
        return f"Reminder #{rid} cancelled."
