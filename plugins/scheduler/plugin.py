"""Scheduler plugin v2 — reminders with snooze, reschedule, at-time, recurring."""

import time
import threading
import sqlite3
import os
import re
from plugins.base import PluginBase
from core.config import get


def _db_path() -> str:
    raw = get("memory", {}).get("db_path", "~/.jarvis/memory.db")
    return os.path.expanduser(raw)


def _init_db(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS reminders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            fire_at    REAL    NOT NULL,
            message    TEXT    NOT NULL,
            repeat     TEXT    DEFAULT '',
            snooze_min INTEGER DEFAULT 5,
            done       INTEGER DEFAULT 0,
            created_at REAL    DEFAULT (strftime('%s','now'))
        );
    """)
    con.commit()
    con.close()


# ── time parsing ──────────────────────────────────────────────────

_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}

_REPEAT_MAP = {
    "minutely": 60, "hourly": 3600, "daily": 86400,
    "weekly": 604800, "every minute": 60, "every hour": 3600,
    "every day": 86400, "every week": 604800,
}


def _parse_delay(text: str) -> int | None:
    """Parse 'in X unit' or 'X unit' patterns. Returns seconds or None."""
    m = re.search(r"\bin\s+(\d+)\s*(\w+)", text.lower())
    if not m:
        m = re.search(r"(\d+)\s*(\w+)\s*(?:from now|later)", text.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2).lower().rstrip("s") + "s"
        mult = _UNITS.get(unit) or _UNITS.get(unit.rstrip("s"))
        if mult:
            return n * mult
    return None


def _parse_at_time(text: str) -> float | None:
    """Parse 'at HH:MM' or 'at H:MM am/pm'. Returns epoch or None."""
    m = re.search(r"\bat\s+(\d{1,2}):(\d{2})\s*(am|pm)?", text.lower())
    if not m:
        m = re.search(r"\bat\s+(\d{1,2})\s*(am|pm)", text.lower())
        if m:
            hour = int(m.group(1))
            meridiem = m.group(2)
            minute = 0
        else:
            return None
    else:
        hour, minute = int(m.group(1)), int(m.group(2))
        meridiem = m.group(3) or ""

    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    now   = time.localtime()
    epoch = time.mktime((
        now.tm_year, now.tm_mon, now.tm_mday,
        hour, minute, 0, now.tm_wday, now.tm_yday, now.tm_isdst
    ))
    if epoch < time.time():
        epoch += 86400  # next day if time already passed
    return epoch


def _parse_repeat(text: str) -> str:
    t = text.lower()
    for k in _REPEAT_MAP:
        if k in t:
            return k.replace("every ", "")
    return ""


def _strip_reminder_boilerplate(text: str) -> str:
    text = re.sub(r"remind(\s+me)?(\s+to)?", "", text, flags=re.I)
    text = re.sub(r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?", "", text, flags=re.I)
    text = re.sub(r"\bin\s+\d+\s*\w+", "", text, flags=re.I)
    text = re.sub(r"every\s+\w+", "", text, flags=re.I)
    text = re.sub(r"(schedule[dr]?|reminder)", "", text, flags=re.I)
    return text.strip(" ,.:;\"'")


# ── notification ───────────────────────────────────────────────

def _notify(message: str):
    import platform
    import subprocess
    sys = platform.system()
    try:
        if sys == "Darwin":
            subprocess.run(["osascript", "-e",
                f'display notification "{message}" with title "Jarvis Reminder"'],
                check=False)
        elif sys == "Windows":
            # Use PowerShell toast
            ps = (
                f'[Windows.UI.Notifications.ToastNotificationManager, '
                f'Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;'
                f'$t = [Windows.UI.Notifications.ToastNotificationManager]'
                f'::GetTemplateContent(0);'
                f'$t.GetElementsByTagName("text")[0].InnerText = "{message}";'
                f'$n = [Windows.UI.Notifications.ToastNotification]::new($t);'
                f'[Windows.UI.Notifications.ToastNotificationManager]'
                f'::CreateToastNotifier("Jarvis").Show($n)'
            )
            subprocess.run(["powershell", "-Command", ps], check=False)
        else:
            subprocess.run(["notify-send", "-u", "normal", "Jarvis Reminder", message],
                           check=False)
    except Exception:
        pass
    print(f"\n\033[93m⏰ [Reminder] {message}\033[0m\nYou: ", end="", flush=True)


# ── background ticker ─────────────────────────────────────────────

_ticker_started = False
_ticker_lock    = threading.Lock()


def _ticker(path: str):
    while True:
        try:
            con = sqlite3.connect(path, timeout=5)
            now = time.time()
            due = con.execute(
                "SELECT id, message, repeat, snooze_min "
                "FROM reminders WHERE fire_at<=? AND done=0",
                (now,)
            ).fetchall()
            for rid, msg, repeat, snooze_min in due:
                _notify(msg)
                if repeat:
                    interval = _REPEAT_MAP.get(repeat, 86400)
                    con.execute("UPDATE reminders SET fire_at=? WHERE id=?",
                                (now + interval, rid))
                else:
                    con.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
            if due:
                con.commit()
            con.close()
        except Exception:
            pass
        time.sleep(5)


def _ensure_ticker(path: str):
    global _ticker_started
    with _ticker_lock:
        if not _ticker_started:
            threading.Thread(target=_ticker, args=(path,), daemon=True).start()
            _ticker_started = True


# ── Plugin ─────────────────────────────────────────────────────

class Plugin(PluginBase):
    priority = 22

    def __init__(self):
        self._db = _db_path()
        _init_db(self._db)
        _ensure_ticker(self._db)

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in (
            "remind", "reminder", "schedule", "snooze", "reschedule",
        ))

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(k in t for k in ("list reminder", "show reminder", "my reminder")): return self._list()
        if any(k in t for k in ("cancel reminder", "delete reminder")): return self._cancel(text)
        if "snooze" in t: return self._snooze(text)
        if "reschedule" in t: return self._reschedule(text)
        return self._add(text)

    # ── public API called by dispatcher ──────────────────────────────

    def add_structured(self, delay_seconds: int = 0, message: str = "Reminder!",
                       repeat: str = "", fire_at: float = 0.0,
                       snooze_min: int = 5) -> str:
        at = fire_at if fire_at else time.time() + max(delay_seconds, 1)
        con = sqlite3.connect(self._db)
        cur = con.execute(
            "INSERT INTO reminders (fire_at, message, repeat, snooze_min) VALUES (?,?,?,?)",
            (at, message, repeat, snooze_min)
        )
        rid = cur.lastrowid
        con.commit(); con.close()
        when = time.strftime("%d %b %H:%M", time.localtime(at))
        rep  = f"  [↺ {repeat}]" if repeat else ""
        return f"⏰ Reminder #{rid} set for {when}{rep}: {message}"

    def _add(self, text: str) -> str:
        fire_at = _parse_at_time(text)
        delay   = None if fire_at else _parse_delay(text)
        if not fire_at and delay is None:
            return (
                "Could not parse time. Try:\n"
                "  remind me in 20 minutes to call John\n"
                "  remind me at 3pm to review PR\n"
                "  remind me every day to drink water"
            )
        msg    = _strip_reminder_boilerplate(text) or "Reminder!"
        repeat = _parse_repeat(text)
        return self.add_structured(
            delay_seconds=int(delay or 0),
            message=msg, repeat=repeat, fire_at=fire_at or 0.0
        )

    def _list(self) -> str:
        con  = sqlite3.connect(self._db)
        rows = con.execute(
            "SELECT id, fire_at, message, repeat FROM reminders "
            "WHERE done=0 ORDER BY fire_at"
        ).fetchall()
        con.close()
        if not rows:
            return "No pending reminders."
        lines = []
        for rid, fa, msg, rep in rows:
            when = time.strftime("%d %b %H:%M", time.localtime(fa))
            rep_s = f" [↺{rep}]" if rep else ""
            lines.append(f"#{rid:<3} {when}{rep_s:<12}  {msg}")
        return "Reminders:\n" + "\n".join(lines)

    def _cancel(self, text: str) -> str:
        m = re.search(r"#?(\d+)", text)
        if not m:
            return "Usage: cancel reminder <id>"
        rid = int(m.group(1))
        con = sqlite3.connect(self._db)
        affected = con.execute(
            "UPDATE reminders SET done=1 WHERE id=? AND done=0", (rid,)
        ).rowcount
        con.commit(); con.close()
        return f"Reminder #{rid} cancelled." if affected else f"Reminder #{rid} not found."

    def _snooze(self, text: str) -> str:
        """Snooze a reminder: 'snooze reminder 3 for 10 minutes'"""
        m_id  = re.search(r"#?(\d+)", text)
        delay = _parse_delay(text) or 300  # default 5 min
        if not m_id:
            return "Usage: snooze reminder <id> for <time>"
        rid = int(m_id.group(1))
        new_fire = time.time() + delay
        con = sqlite3.connect(self._db)
        affected = con.execute(
            "UPDATE reminders SET fire_at=?, done=0 WHERE id=?",
            (new_fire, rid)
        ).rowcount
        con.commit(); con.close()
        if not affected:
            return f"Reminder #{rid} not found."
        when = time.strftime("%H:%M", time.localtime(new_fire))
        return f"⏰ Reminder #{rid} snoozed to {when}."

    def _reschedule(self, text: str) -> str:
        """Reschedule: 'reschedule reminder 2 to 5pm'"""
        m_id   = re.search(r"#?(\d+)", text)
        fire_at = _parse_at_time(text)
        delay   = _parse_delay(text) if not fire_at else None
        if not m_id or (not fire_at and not delay):
            return "Usage: reschedule reminder <id> to <time>"
        rid     = int(m_id.group(1))
        new_at  = fire_at or (time.time() + delay)
        con = sqlite3.connect(self._db)
        affected = con.execute(
            "UPDATE reminders SET fire_at=?, done=0 WHERE id=?",
            (new_at, rid)
        ).rowcount
        con.commit(); con.close()
        if not affected:
            return f"Reminder #{rid} not found."
        when = time.strftime("%d %b %H:%M", time.localtime(new_at))
        return f"⏰ Reminder #{rid} rescheduled to {when}."
