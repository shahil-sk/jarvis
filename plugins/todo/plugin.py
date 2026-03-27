"""Todo plugin — full task manager: add, list, complete, delete, edit, priority, tags, due dates."""

import sqlite3
import os
import re
import time
from plugins.base import PluginBase
from core.config import get

_PRIORITIES = {"low": 1, "medium": 2, "med": 2, "high": 3, "urgent": 4, "critical": 4}
_PRI_LABEL  = {1: "low", 2: "med", 3: "high", 4: "urgent"}
_PRI_ICON   = {1: "○", 2: "◑", 3: "●", 4: "⚠️"}
_STATUS_ICON = {"todo": "□", "doing": "▶", "done": "✓", "blocked": "⧗"}


def _db_path() -> str:
    raw = get("memory", {}).get("db_path", "~/.jarvis/memory.db")
    return os.path.expanduser(raw)


def _init_db(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS todos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT    NOT NULL,
            status     TEXT    DEFAULT 'todo',
            priority   INTEGER DEFAULT 2,
            tags       TEXT    DEFAULT '',
            due        TEXT    DEFAULT '',
            project    TEXT    DEFAULT '',
            notes      TEXT    DEFAULT '',
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            updated_at TEXT    DEFAULT (datetime('now','localtime'))
        );
    """)
    con.commit()
    con.close()


# ── parsers ───────────────────────────────────────────────────

def _extract_tags(text: str) -> tuple[str, list]:
    tags = re.findall(r"#(\w+)", text)
    clean = re.sub(r"#\w+", "", text).strip()
    return clean, tags


def _extract_priority(text: str) -> tuple[str, int]:
    m = re.search(r"!!(urgent|critical)|!(high|medium|med|low)", text, re.I)
    if m:
        word  = (m.group(1) or m.group(2)).lower()
        clean = text[:m.start()] + text[m.end():]
        return clean.strip(), _PRIORITIES.get(word, 2)
    # plain word priority
    for word, val in _PRIORITIES.items():
        pat = rf"\b{word}\s+priority\b|\bpriority\s+{word}\b"
        if re.search(pat, text, re.I):
            clean = re.sub(pat, "", text, flags=re.I).strip()
            return clean, val
    return text, 2


def _extract_due(text: str) -> tuple[str, str]:
    """Extract due date keywords: 'today', 'tomorrow', 'YYYY-MM-DD', 'Mon DD'."""
    t = text.lower()
    today = time.strftime("%Y-%m-%d")

    if "today" in t:
        clean = re.sub(r"\btoday\b", "", text, flags=re.I).strip()
        return clean, today
    if "tomorrow" in t:
        due   = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
        clean = re.sub(r"\btomorrow\b", "", text, flags=re.I).strip()
        return clean, due
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return text[:m.start()] + text[m.end():], m.group(1)
    m = re.search(r"by\s+(\w+\s+\d{1,2})", text, re.I)
    if m:
        clean = text[:m.start()] + text[m.end():]
        return clean.strip(), m.group(1)
    return text, ""


def _extract_project(text: str) -> tuple[str, str]:
    m = re.search(r"@(\w+)", text)
    if m:
        return (text[:m.start()] + text[m.end():]).strip(), m.group(1)
    return text, ""


def _fmt_row(row) -> str:
    rid, title, status, pri, tags, due, project, *_ = row
    icon  = _STATUS_ICON.get(status, "□")
    p_ico = _PRI_ICON.get(pri, "○")
    parts = [f"{icon} #{rid:<3} {p_ico} {title}"]
    if project : parts.append(f"@{project}")
    if tags    : parts.append(" ".join(f"#{t}" for t in tags.split(",") if t))
    if due     : parts.append(f"due:{due}")
    return "  ".join(parts)


# ── Plugin ─────────────────────────────────────────────────────

class Plugin(PluginBase):
    priority = 23  # just below scheduler

    def __init__(self):
        self._db = _db_path()
        _init_db(self._db)

    def matches(self, text: str) -> bool:
        return False  # fully intent-routed

    def run(self, text: str, memory) -> str:
        return "Todo plugin is intent-routed."

    # ── add ─────────────────────────────────────────────────────

    def add(self, title: str, priority: int = 2, tags: str = "",
            due: str = "", project: str = "", notes: str = "") -> str:
        """Add with fully structured args (called by dispatcher)."""
        if not title.strip():
            return "Todo title cannot be empty."
        con = sqlite3.connect(self._db)
        cur = con.execute(
            "INSERT INTO todos (title,status,priority,tags,due,project,notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (title.strip(), "todo", priority, tags, due, project, notes)
        )
        tid = cur.lastrowid
        con.commit(); con.close()
        p_lbl = _PRI_LABEL.get(priority, "med")
        extras = "".join([
            f" @{project}" if project else "",
            f" #{tags}"    if tags    else "",
            f" due:{due}"  if due     else "",
        ])
        return f"□ Todo #{tid} added [{p_lbl}]{extras}: {title}"

    def add_from_text(self, text: str) -> str:
        """Parse raw natural language and add todo."""
        # Strip leading verb
        text = re.sub(r"^(add|create|new|todo|task)\s+(todo|task)?\s*:?\s*",
                      "", text, flags=re.I).strip()
        text, project  = _extract_project(text)
        text, due      = _extract_due(text)
        text, priority = _extract_priority(text)
        text, tags     = _extract_tags(text)
        return self.add(text, priority, ",".join(tags), due, project)

    # ── list ─────────────────────────────────────────────────────

    def list_todos(self, status: str = "", tag: str = "",
                   project: str = "", priority: int = 0) -> str:
        where, params = ["1=1"], []
        if status   : where.append("status=?");             params.append(status)
        else        : where.append("status != 'done'")
        if tag      : where.append("tags LIKE ?");          params.append(f"%{tag}%")
        if project  : where.append("project=?");            params.append(project)
        if priority : where.append("priority>=?");          params.append(priority)

        con  = sqlite3.connect(self._db)
        rows = con.execute(
            f"SELECT id,title,status,priority,tags,due,project,notes "
            f"FROM todos WHERE {' AND '.join(where)} ORDER BY priority DESC, id",
            params
        ).fetchall()
        con.close()
        if not rows:
            return "No todos found."
        # group by status
        groups: dict[str, list] = {}
        for row in rows:
            s = row[2]
            groups.setdefault(s, []).append(_fmt_row(row))
        out = []
        for s in ("doing", "todo", "blocked", "done"):
            if s in groups:
                label = {"todo":"To Do","doing":"In Progress","done":"Done","blocked":"Blocked"}[s]
                out.append(f"\n{label}:")
                out.extend(groups[s])
        return "\n".join(out).strip()

    # ── status transitions ─────────────────────────────────────────

    def complete(self, todo_id: int) -> str:
        return self._set_status(todo_id, "done")

    def start(self, todo_id: int) -> str:
        return self._set_status(todo_id, "doing")

    def block(self, todo_id: int) -> str:
        return self._set_status(todo_id, "blocked")

    def reopen(self, todo_id: int) -> str:
        return self._set_status(todo_id, "todo")

    def _set_status(self, todo_id: int, status: str) -> str:
        con = sqlite3.connect(self._db)
        row = con.execute("SELECT title FROM todos WHERE id=?", (todo_id,)).fetchone()
        if not row:
            con.close()
            return f"Todo #{todo_id} not found."
        con.execute(
            "UPDATE todos SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, todo_id)
        )
        con.commit(); con.close()
        icon = _STATUS_ICON.get(status, "□")
        return f"{icon} Todo #{todo_id} marked as {status}: {row[0]}"

    # ── edit ──────────────────────────────────────────────────────

    def edit(self, todo_id: int, title: str = "", priority: int = 0,
             tags: str = "", due: str = "", project: str = "",
             notes: str = "") -> str:
        con = sqlite3.connect(self._db)
        row = con.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
        if not row:
            con.close()
            return f"Todo #{todo_id} not found."
        fields, params = [], []
        if title   : fields.append("title=?");    params.append(title)
        if priority: fields.append("priority=?"); params.append(priority)
        if tags    : fields.append("tags=?");     params.append(tags)
        if due     : fields.append("due=?");      params.append(due)
        if project : fields.append("project=?");  params.append(project)
        if notes   : fields.append("notes=?");    params.append(notes)
        if not fields:
            con.close()
            return "Nothing to update."
        fields.append("updated_at=datetime('now','localtime')")
        params.append(todo_id)
        con.execute(f"UPDATE todos SET {', '.join(fields)} WHERE id=?", params)
        con.commit(); con.close()
        return f"✏️ Todo #{todo_id} updated."

    # ── delete ─────────────────────────────────────────────────────

    def delete(self, todo_id: int) -> str:
        con = sqlite3.connect(self._db)
        row = con.execute("SELECT title FROM todos WHERE id=?", (todo_id,)).fetchone()
        if not row:
            con.close()
            return f"Todo #{todo_id} not found."
        con.execute("DELETE FROM todos WHERE id=?", (todo_id,))
        con.commit(); con.close()
        return f"🗑️ Todo #{todo_id} deleted: {row[0]}"

    # ── search ────────────────────────────────────────────────────

    def search(self, query: str) -> str:
        con  = sqlite3.connect(self._db)
        rows = con.execute(
            "SELECT id,title,status,priority,tags,due,project,notes "
            "FROM todos WHERE title LIKE ? OR tags LIKE ? OR notes LIKE ? OR project LIKE ?",
            (f"%{query}%",) * 4
        ).fetchall()
        con.close()
        if not rows:
            return f"No todos matching '{query}'."
        return "\n".join(_fmt_row(r) for r in rows)

    # ── due today / overdue ───────────────────────────────────────

    def due_today(self) -> str:
        today = time.strftime("%Y-%m-%d")
        con   = sqlite3.connect(self._db)
        rows  = con.execute(
            "SELECT id,title,status,priority,tags,due,project,notes "
            "FROM todos WHERE due<=? AND status!='done' ORDER BY priority DESC",
            (today,)
        ).fetchall()
        con.close()
        if not rows:
            return "Nothing due today ✅"
        return "Due today / overdue:\n" + "\n".join(_fmt_row(r) for r in rows)

    # ── stats ──────────────────────────────────────────────────────

    def stats(self) -> str:
        con = sqlite3.connect(self._db)
        rows = con.execute(
            "SELECT status, COUNT(*) FROM todos GROUP BY status"
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
        overdue_count = con.execute(
            "SELECT COUNT(*) FROM todos WHERE due!='' AND due<? AND status!='done'",
            (time.strftime("%Y-%m-%d"),)
        ).fetchone()[0]
        con.close()
        counts = {r[0]: r[1] for r in rows}
        lines = [
            f"Total     : {total}",
            f"To Do     : {counts.get('todo', 0)}",
            f"In Progress: {counts.get('doing', 0)}",
            f"Done      : {counts.get('done', 0)}",
            f"Blocked   : {counts.get('blocked', 0)}",
            f"Overdue   : {overdue_count}",
        ]
        return "Todo Stats:\n" + "\n".join(lines)
