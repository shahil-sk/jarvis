"""core/db.py — Shared SQLite connection manager for Jarvis.

All code (core + plugins) that needs SQLite should use this module instead of
opening raw sqlite3.connect() calls directly. Benefits:

  • WAL mode       — readers never block writers; writers never block readers.
  • Connection pool — one long-lived connection per DB path, thread-safe.
  • Migrations      — schema changes are tracked in a `_migrations` table;
                       safe to run on every startup (idempotent).
  • Helpers         — execute(), fetchall(), fetchone(), insert() wrap the
                       common pattern of connect → cursor → commit → close.

Usage (from any plugin or core module):

    from core.db import DB

    db = DB()                        # uses default memory.db path
    db = DB("/path/to/custom.db")    # custom path (for plugin-owned DBs)

    db.execute("INSERT INTO notes (ts, tag, content) VALUES (?, ?, ?)", (ts, tag, text))
    rows = db.fetchall("SELECT * FROM notes WHERE tag=?", (tag,))
    row  = db.fetchone("SELECT * FROM notes WHERE id=?", (nid,))
    rid  = db.insert("INSERT INTO notes (ts, tag, content) VALUES (?, ?, ?)", (ts, tag, text))
    db.close()   # optional — connections are kept alive for the process lifetime
"""

import sqlite3
import threading
import os
import time
from core.config import get

_DEFAULT_DB = os.path.expanduser("~/.jarvis/memory.db")

# Thread-local connection pool: {db_path: connection}
_pool: dict[str, sqlite3.Connection] = {}
_pool_lock = threading.Lock()


def _connect(path: str) -> sqlite3.Connection:
    """Return (or create) a cached connection for `path`."""
    with _pool_lock:
        if path not in _pool or not _is_alive(_pool[path]):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            con = sqlite3.connect(path, check_same_thread=False, timeout=10)
            con.row_factory = sqlite3.Row          # rows accessible by column name
            con.execute("PRAGMA journal_mode=WAL")  # WAL: concurrent readers + writers
            con.execute("PRAGMA synchronous=NORMAL") # balance durability / speed
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA temp_store=MEMORY")
            con.commit()
            _pool[path] = con
        return _pool[path]


def _is_alive(con: sqlite3.Connection) -> bool:
    try:
        con.execute("SELECT 1")
        return True
    except Exception:
        return False


class DB:
    """Thin wrapper around a SQLite connection with migration support."""

    def __init__(self, path: str | None = None):
        cfg = get("memory", {})
        self._path = os.path.expanduser(
            path or cfg.get("db_path", _DEFAULT_DB)
        )
        self._con  = _connect(self._path)
        self._ensure_migrations_table()

    # ------------------------------------------------------------------ #
    # Public query helpers
    # ------------------------------------------------------------------ #

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a statement (INSERT/UPDATE/DELETE/CREATE). Auto-commits."""
        try:
            cur = self._con.execute(sql, params)
            self._con.commit()
            return cur
        except sqlite3.OperationalError as exc:
            # Reconnect once on "database is locked" or closed connection
            self._con = _connect.__wrapped__(self._path) if hasattr(_connect, "__wrapped__") else self._reconnect()
            cur = self._con.execute(sql, params)
            self._con.commit()
            return cur

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run a SELECT and return all rows as dicts."""
        cur = self._con.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        """Run a SELECT and return the first row as a dict, or None."""
        cur = self._con.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def insert(self, sql: str, params: tuple = ()) -> int:
        """Execute an INSERT and return the new row's id."""
        cur = self.execute(sql, params)
        return cur.lastrowid

    def close(self) -> None:
        """Remove from pool and close. Usually not needed."""
        with _pool_lock:
            self._pool.pop(self._path, None)
        try:
            self._con.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Migration engine
    # ------------------------------------------------------------------ #

    def _ensure_migrations_table(self) -> None:
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT UNIQUE NOT NULL,
                applied REAL NOT NULL
            )
        """)
        self._con.commit()

    def _applied(self, name: str) -> bool:
        row = self._con.execute(
            "SELECT 1 FROM _migrations WHERE name=?", (name,)
        ).fetchone()
        return row is not None

    def migrate(self, name: str, sql: str) -> bool:
        """Apply a named migration exactly once. Returns True if it ran.

        Example::

            db.migrate(
                "001_add_priority_to_notes",
                "ALTER TABLE notes ADD COLUMN priority INTEGER DEFAULT 0"
            )
        """
        if self._applied(name):
            return False
        try:
            self._con.executescript(sql)          # executescript auto-commits
            self._con.execute(
                "INSERT INTO _migrations (name, applied) VALUES (?, ?)",
                (name, time.time())
            )
            self._con.commit()
            return True
        except Exception as exc:
            print(f"[db] migration '{name}' failed: {exc}")
            return False

    def _reconnect(self) -> sqlite3.Connection:
        with _pool_lock:
            _pool.pop(self._path, None)
        return _connect(self._path)

    @property
    def path(self) -> str:
        return self._path
