"""Memory v2 — dual-layer store: in-session ring buffer + SQLite long-term.

Changes from v1
---------------
• Uses core.db.DB instead of raw sqlite3 calls — gains WAL mode, connection
  pooling, and the migration engine automatically.
• Schema migrations are applied on every startup via DB.migrate() — safe to
  run on existing databases (idempotent).
• New `intents` table — every classified intent + trigger is logged so you
  can replay history, debug misclassifications, and build analytics.
• Indexes on `history(ts)` and `notes(tag, ts)` for fast queries.
• `search_history()` — full-text search over long-term history.
• `stats()` — returns DB row counts for diagnostics.
• All write methods are wrapped in try/except; a DB hiccup never crashes
  the REPL.
"""

import time
import os
from collections import deque
from core.config import get
from core.db import DB

_DEFAULT_DB = os.path.expanduser("~/.jarvis/memory.db")


class Memory:
    def __init__(self):
        cfg           = get("memory", {}) or {}
        self._max     = cfg.get("max_entries", 50)
        self._store: deque = deque(maxlen=self._max)
        self._persist = cfg.get("persist", True)
        self._db: DB | None = None

        if self._persist:
            db_path   = os.path.expanduser(cfg.get("db_path", _DEFAULT_DB))
            self._db  = DB(db_path)
            self._run_migrations()

    # ------------------------------------------------------------------ #
    # Schema migrations — run on every startup, idempotent
    # ------------------------------------------------------------------ #

    def _run_migrations(self) -> None:
        db = self._db

        # 001 — baseline tables (history + notes)
        db.migrate("001_baseline", """
            CREATE TABLE IF NOT EXISTS history (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      REAL    NOT NULL,
                role    TEXT    NOT NULL,
                content TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      REAL    NOT NULL,
                tag     TEXT    DEFAULT '',
                content TEXT    NOT NULL
            );
        """)

        # 002 — indexes for faster queries
        db.migrate("002_indexes", """
            CREATE INDEX IF NOT EXISTS idx_history_ts  ON history(ts);
            CREATE INDEX IF NOT EXISTS idx_notes_tag   ON notes(tag);
            CREATE INDEX IF NOT EXISTS idx_notes_ts    ON notes(ts);
        """)

        # 003 — intent log: stores every classified intent for debugging / analytics
        db.migrate("003_intent_log", """
            CREATE TABLE IF NOT EXISTS intent_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      REAL    NOT NULL,
                input   TEXT    NOT NULL,
                intent  TEXT    NOT NULL,
                trigger TEXT    DEFAULT '',
                args    TEXT    DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_intent_log_ts     ON intent_log(ts);
            CREATE INDEX IF NOT EXISTS idx_intent_log_intent ON intent_log(intent);
        """)

        # 004 — add priority column to notes (optional feature)
        db.migrate("004_notes_priority", """
            ALTER TABLE notes ADD COLUMN priority INTEGER DEFAULT 0;
        """)

        # 005 — add session_id to history (groups messages per REPL session)
        db.migrate("005_history_session", """
            ALTER TABLE history ADD COLUMN session_id TEXT DEFAULT '';
        """)

    # ------------------------------------------------------------------ #
    # Session (in-memory ring buffer)
    # ------------------------------------------------------------------ #

    def add(self, role: str, content: str) -> None:
        entry = {"role": role, "content": content, "ts": time.time()}
        self._store.append(entry)
        if self._persist and self._db:
            try:
                self._db.execute(
                    "INSERT INTO history (ts, role, content) VALUES (?, ?, ?)",
                    (entry["ts"], role, content)
                )
            except Exception as exc:
                print(f"[memory] write failed: {exc}")

    def history(self) -> list:
        """Full in-session ring buffer."""
        return list(self._store)

    def last(self, n: int = 5) -> list:
        """Last n entries from the in-session buffer."""
        return list(self._store)[-n:]

    def clear(self) -> None:
        """Clear the in-session buffer (does not touch SQLite)."""
        self._store.clear()

    # ------------------------------------------------------------------ #
    # Long-term (SQLite history)
    # ------------------------------------------------------------------ #

    def recall(self, n: int = 20) -> list:
        """Last n messages from SQLite history, oldest-first."""
        if not self._db:
            return []
        try:
            rows = self._db.fetchall(
                "SELECT ts, role, content FROM history ORDER BY id DESC LIMIT ?", (n,)
            )
            return list(reversed(rows))
        except Exception:
            return []

    def search_history(self, query: str, limit: int = 20) -> list:
        """Full-text search over long-term history content."""
        if not self._db:
            return []
        try:
            return self._db.fetchall(
                "SELECT ts, role, content FROM history "
                "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit)
            )
        except Exception:
            return []

    def forget(self) -> bool:
        """Wipe all SQLite history and clear session buffer."""
        if not self._db:
            return False
        try:
            self._db.execute("DELETE FROM history")
            self.clear()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Intent log
    # ------------------------------------------------------------------ #

    def log_intent(
        self,
        user_input: str,
        intent: str,
        trigger: str = "",
        args: dict | None = None,
    ) -> None:
        """Persist a classified intent to the intent_log table."""
        if not self._db:
            return
        try:
            import json
            self._db.execute(
                "INSERT INTO intent_log (ts, input, intent, trigger, args) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), user_input, intent, trigger, json.dumps(args or {}))
            )
        except Exception as exc:
            print(f"[memory] intent_log write failed: {exc}")

    def recent_intents(self, n: int = 10) -> list:
        """Return the last n logged intents (newest first)."""
        if not self._db:
            return []
        try:
            return self._db.fetchall(
                "SELECT ts, input, intent, trigger, args "
                "FROM intent_log ORDER BY id DESC LIMIT ?", (n,)
            )
        except Exception:
            return []

    def intent_stats(self) -> list:
        """Return intent frequency counts, most common first."""
        if not self._db:
            return []
        try:
            return self._db.fetchall(
                "SELECT intent, COUNT(*) as count "
                "FROM intent_log GROUP BY intent ORDER BY count DESC"
            )
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    # Notes
    # ------------------------------------------------------------------ #

    def save_note(self, content: str, tag: str = "", priority: int = 0) -> int:
        """Persist a note and return its id."""
        if not self._db:
            return -1
        try:
            return self._db.insert(
                "INSERT INTO notes (ts, tag, content, priority) VALUES (?, ?, ?, ?)",
                (time.time(), tag, content, priority)
            )
        except Exception:
            return -1

    def get_notes(
        self,
        tag: str = "",
        limit: int = 20,
        search: str = "",
    ) -> list:
        """Fetch notes with optional tag filter and/or full-text search."""
        if not self._db:
            return []
        try:
            if tag and search:
                return self._db.fetchall(
                    "SELECT id, ts, tag, content, priority FROM notes "
                    "WHERE tag=? AND content LIKE ? ORDER BY id DESC LIMIT ?",
                    (tag, f"%{search}%", limit)
                )
            elif tag:
                return self._db.fetchall(
                    "SELECT id, ts, tag, content, priority FROM notes "
                    "WHERE tag=? ORDER BY id DESC LIMIT ?",
                    (tag, limit)
                )
            elif search:
                return self._db.fetchall(
                    "SELECT id, ts, tag, content, priority FROM notes "
                    "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                    (f"%{search}%", limit)
                )
            else:
                return self._db.fetchall(
                    "SELECT id, ts, tag, content, priority FROM notes "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
        except Exception:
            return []

    def delete_note(self, nid: int) -> bool:
        if not self._db:
            return False
        try:
            self._db.execute("DELETE FROM notes WHERE id=?", (nid,))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    def stats(self) -> dict:
        """Return row counts for all tables — useful for debugging."""
        if not self._db:
            return {}
        try:
            def count(table):
                row = self._db.fetchone(f"SELECT COUNT(*) as n FROM {table}")
                return row["n"] if row else 0
            return {
                "history"    : count("history"),
                "notes"      : count("notes"),
                "intent_log" : count("intent_log"),
                "db_path"    : self._db.path,
            }
        except Exception:
            return {}
