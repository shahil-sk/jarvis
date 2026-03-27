"""Memory — dual-layer: in-session ring buffer + SQLite long-term store."""

import sqlite3
import time
import os
from collections import deque
from core.config import get

_DB_PATH = os.path.expanduser("~/.jarvis/memory.db")


def _init_db(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      REAL NOT NULL,
            role    TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      REAL NOT NULL,
            tag     TEXT DEFAULT '',
            content TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


class Memory:
    def __init__(self):
        self._max   = get("memory", {}).get("max_entries", 50)
        self._store: deque = deque(maxlen=self._max)
        self._db    = get("memory", {}).get("db_path", _DB_PATH)
        self._persist = get("memory", {}).get("persist", True)
        if self._persist:
            _init_db(self._db)

    # ── session (in-memory) ────────────────────────────────────────────

    def add(self, role: str, content: str):
        entry = {"role": role, "content": content, "ts": time.time()}
        self._store.append(entry)
        if self._persist:
            self._write_history(role, content)

    def history(self) -> list:
        return list(self._store)

    def last(self, n: int = 5) -> list:
        return list(self._store)[-n:]

    def clear(self):
        self._store.clear()

    # ── long-term (SQLite) ─────────────────────────────────────────────

    def _write_history(self, role: str, content: str):
        try:
            con = sqlite3.connect(self._db)
            con.execute("INSERT INTO history (ts, role, content) VALUES (?, ?, ?)",
                        (time.time(), role, content))
            con.commit()
            con.close()
        except Exception:
            pass

    def recall(self, n: int = 20) -> list:
        """Fetch last n exchanges from long-term store."""
        try:
            con = sqlite3.connect(self._db)
            rows = con.execute(
                "SELECT ts, role, content FROM history ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
            con.close()
            return [{"ts": r[0], "role": r[1], "content": r[2]} for r in reversed(rows)]
        except Exception:
            return []

    def forget(self):
        """Wipe all long-term history."""
        try:
            con = sqlite3.connect(self._db)
            con.execute("DELETE FROM history")
            con.commit()
            con.close()
            self.clear()
            return True
        except Exception:
            return False

    # ── notes (via Notes plugin, but exposed here for shared DB) ───────

    def save_note(self, content: str, tag: str = "") -> int:
        con = sqlite3.connect(self._db)
        cur = con.execute("INSERT INTO notes (ts, tag, content) VALUES (?, ?, ?)",
                          (time.time(), tag, content))
        nid = cur.lastrowid
        con.commit()
        con.close()
        return nid

    def get_notes(self, tag: str = "", limit: int = 20) -> list:
        con = sqlite3.connect(self._db)
        if tag:
            rows = con.execute(
                "SELECT id, ts, tag, content FROM notes WHERE tag=? ORDER BY id DESC LIMIT ?",
                (tag, limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, ts, tag, content FROM notes ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        con.close()
        return [{"id": r[0], "ts": r[1], "tag": r[2], "content": r[3]} for r in rows]

    def delete_note(self, nid: int) -> bool:
        try:
            con = sqlite3.connect(self._db)
            con.execute("DELETE FROM notes WHERE id=?", (nid,))
            con.commit()
            con.close()
            return True
        except Exception:
            return False
