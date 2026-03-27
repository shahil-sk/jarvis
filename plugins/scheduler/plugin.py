"""Scheduler plugin v3 — migrated to core.db (WAL, migrations, no raw sqlite3).

All SQLite access now goes through core.db.DB:
  • WAL mode             — background ticker and REPL never block each other.
  • Single migration      — schema is applied exactly once on first run.
  • No sqlite3 imports    — the plugin itself only imports from core.db.

Everything else (time parsing, repeat logic, notifications, snooze,
reschedule) is unchanged from v2.
"""

import time
import threading
import os
import re
from plugins.base import PluginBase
from core.config import get
from core.db import DB


# ── time parsing helpers ───────────────────────────────────────────────────

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
    m = re.search(r"\bin\s+(\d+)\s*(\w+)", text.lower())
    if not m:
        m = re.search(r"(\d+)\s*(\w+)\s*(?:from now|later)", text.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        mult = _UNITS.get(unit) or _UNITS.get(unit.rstrip("s"))
        if mult:
            return n * mult
    return None


def _parse_at_time(text: str) -> float | None:
    m = re.search(r"\bat\s+(\d{1,2}):(\d{2})\s*(am|pm)?", text.lower())
    if not m:
        m = re.search(r"\bat\s+(\d{1,2})\s*(am|pm)", text.lower())
        if m:
            hour, minute, meridiem = int(m.group(1)), 0, m.group(2)
        else:
            return None
    else:
        hour, minute, meridiem = int(m.group(1)), int(m.group(2)), (m.group(3) or "")

    if meridiem == "pm" and hour != 12: hour += 12
    elif meridiem == "am" and hour == 12: hour = 0

    now   = time.localtime()
    epoch = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                         hour, minute, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
    return epoch if epoch > time.time() else epoch + 86400


def _parse_repeat(text: str) -> str:
    t = text.lower()
    for k in _REPEAT_MAP:
        if k in t:
            return k.replace("every ", "")
    return ""


def _strip_boilerplate(text: str) -> str:
    text = re.sub(r"remind(\s+me)?(\s+to)?", "", text, flags=re.I)
    text = re.sub(r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?", "", text, flags=re.I)
    text = re.sub(r"\bin\s+\d+\s*\w+", "", text, flags=re.I)
    text = re.sub(r"every\s+\w+", "", text, flags=re.I)
    text = re.sub(r"(schedule[dr]?|reminder)", "", text, flags=re.I)
    return text.strip(" ,.:;\"'")


# ── notification ───────────────────────────────────────────────────────────

def _notify(message: str) -> None:
    import platform, subprocess
    sys = platform.system()
    try:
        if sys == "Darwin":
            subprocess.run(["osascript", "-e",
                f'display notification "{message}" with title "Jarvis Reminder"'],
                check=False)
        elif sys == "Windows":
            ps = (
                f'[Windows.UI.Notifications.ToastNotificationManager,'
                f'Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;'
                f'$t=[Windows.UI.Notifications.ToastNotificationManager]'
                f'::GetTemplateContent(0);'
                f'$t.GetElementsByTagName("text")[0].InnerText="{message}";'
                f'$n=[Windows.UI.Notifications.ToastNotification]::new($t);'
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


# ── background ticker ──────────────────────────────────────────────────────
# Uses its own DB() instance so the ticker thread has its own connection.

_ticker_started = False
_ticker_lock    = threading.Lock()


def _ticker(db_path: str) -> None:
    db = DB(db_path)
    while True:
        try:
            now = time.time()
            due = db.fetchall(
                "SELECT id, message, repeat FROM reminders "
                "WHERE fire_at<=? AND done=0", (now,)
            )
            for row in due:
                _notify(row["message"])
                if row["repeat"]:
                    interval = _REPEAT_MAP.get(row["repeat"], 86400)
                    db.execute("UPDATE reminders SET fire_at=? WHERE id=?",
                               (now + interval, row["id"]))
                else:
                    db.execute("UPDATE reminders SET done=1 WHERE id=?",
                               (row["id"],))
        except Exception as exc:
            print(f"[scheduler ticker] {exc}")
        time.sleep(5)


def _ensure_ticker(db_path: str) -> None:
    global _ticker_started
    with _ticker_lock:
        if not _ticker_started:
            threading.Thread(target=_ticker, args=(db_path,), daemon=True).start()
            _ticker_started = True


# ── Plugin ─────────────────────────────────────────────────────────────────

class Plugin(PluginBase):
    priority = 22

    def __init__(self):
        self._db = DB()
        self._db.migrate("scheduler_001_reminders", """
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                fire_at    REAL    NOT NULL,
                message    TEXT    NOT NULL,
                repeat     TEXT    DEFAULT '',
                snooze_min INTEGER DEFAULT 5,
                done       INTEGER DEFAULT 0,
                created_at REAL    DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_fire ON reminders(fire_at, done);
        """)
        _ensure_ticker(self._db.path)

    def matches(self, text: str) -> bool:
        return any(kw in text.lower() for kw in
                   ("remind", "reminder", "schedule", "snooze", "reschedule"))

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(k in t for k in ("list reminder", "show reminder", "my reminder")): return self._list()
        if any(k in t for k in ("cancel reminder", "delete reminder")): return self._cancel(text)
        if "snooze"      in t: return self._snooze(text)
        if "reschedule"  in t: return self._reschedule(text)
        return self._add(text)

    # ------------------------------------------------------------------ #
    # Public API called directly by dispatcher
    # ------------------------------------------------------------------ #

    def add_structured(
        self,
        delay_seconds: int  = 0,
        message: str        = "Reminder!",
        repeat: str         = "",
        fire_at: float      = 0.0,
        snooze_min: int     = 5,
    ) -> str:
        at  = fire_at if fire_at else time.time() + max(int(delay_seconds), 1)
        rid = self._db.insert(
            "INSERT INTO reminders (fire_at, message, repeat, snooze_min) VALUES (?,?,?,?)",
            (at, message, repeat, snooze_min)
        )
        when = time.strftime("%d %b %H:%M", time.localtime(at))
        rep  = f"  [↺ {repeat}]" if repeat else ""
        return f"⏰ Reminder #{rid} set for {when}{rep}: {message}"

    # ------------------------------------------------------------------ #
    # Internal handlers
    # ------------------------------------------------------------------ #

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
        msg    = _strip_boilerplate(text) or "Reminder!"
        repeat = _parse_repeat(text)
        return self.add_structured(
            delay_seconds=int(delay or 0),
            message=msg, repeat=repeat,
            fire_at=fire_at or 0.0
        )

    def _list(self) -> str:
        rows = self._db.fetchall(
            "SELECT id, fire_at, message, repeat FROM reminders "
            "WHERE done=0 ORDER BY fire_at"
        )
        if not rows:
            return "No pending reminders."
        lines = []
        for r in rows:
            when  = time.strftime("%d %b %H:%M", time.localtime(r["fire_at"]))
            rep_s = f" [↺{r['repeat']}]" if r["repeat"] else ""
            lines.append(f"#{r['id']:<3} {when}{rep_s:<12}  {r['message']}")
        return "Reminders:\n" + "\n".join(lines)

    def _cancel(self, text: str) -> str:
        m = re.search(r"#?(\d+)", text)
        if not m:
            return "Usage: cancel reminder <id>"
        rid      = int(m.group(1))
        affected = self._db.execute(
            "UPDATE reminders SET done=1 WHERE id=? AND done=0", (rid,)
        ).rowcount
        return f"Reminder #{rid} cancelled." if affected else f"Reminder #{rid} not found."

    def _snooze(self, text: str) -> str:
        m_id  = re.search(r"#?(\d+)", text)
        delay = _parse_delay(text) or 300
        if not m_id:
            return "Usage: snooze reminder <id> for <time>"
        rid      = int(m_id.group(1))
        new_fire = time.time() + delay
        affected = self._db.execute(
            "UPDATE reminders SET fire_at=?, done=0 WHERE id=?",
            (new_fire, rid)
        ).rowcount
        if not affected:
            return f"Reminder #{rid} not found."
        return f"⏰ Reminder #{rid} snoozed to {time.strftime('%H:%M', time.localtime(new_fire))}."

    def _reschedule(self, text: str) -> str:
        m_id   = re.search(r"#?(\d+)", text)
        fire_at = _parse_at_time(text)
        delay   = _parse_delay(text) if not fire_at else None
        if not m_id or (not fire_at and not delay):
            return "Usage: reschedule reminder <id> to <time>"
        rid    = int(m_id.group(1))
        new_at = fire_at or (time.time() + delay)
        affected = self._db.execute(
            "UPDATE reminders SET fire_at=?, done=0 WHERE id=?",
            (new_at, rid)
        ).rowcount
        if not affected:
            return f"Reminder #{rid} not found."
        return f"⏰ Reminder #{rid} rescheduled to {time.strftime('%d %b %H:%M', time.localtime(new_at))}."
