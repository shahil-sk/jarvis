"""Todo plugin v2 — migrated to core.db (WAL, migrations, no raw sqlite3).

Status values: active | in_progress | blocked | done
Priority    : 1=low  2=medium  3=high  4=urgent
"""

import time
import re
from plugins.base import PluginBase
from core.db import DB

_STATUS  = ("active", "in_progress", "blocked", "done")
_PRI_MAP = {1: "low", 2: "medium", 3: "high", 4: "urgent"}


class Plugin(PluginBase):
    priority = 30

    def __init__(self):
        self._db = DB()
        self._db.migrate("todo_001_baseline", """
            CREATE TABLE IF NOT EXISTS todos (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL    NOT NULL,
                updated_at REAL    NOT NULL,
                title      TEXT    NOT NULL,
                status     TEXT    DEFAULT 'active',
                priority   INTEGER DEFAULT 2,
                tags       TEXT    DEFAULT '',
                due        TEXT    DEFAULT '',
                project    TEXT    DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_todos_status  ON todos(status);
            CREATE INDEX IF NOT EXISTS idx_todos_project ON todos(project);
            CREATE INDEX IF NOT EXISTS idx_todos_due     ON todos(due);
        """)

    # ------------------------------------------------------------------ #
    # matches / run  (keyword-fallback compatibility)
    # ------------------------------------------------------------------ #

    def matches(self, text: str) -> bool:
        return any(kw in text.lower() for kw in
                   ("todo", "task", "add task", "list task", "due today"))

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if "add todo"   in t or "add task" in t: return self._run_add(text)
        if "list todo"  in t or "list task" in t: return self.list_todos()
        if "todo stats" in t:                     return self.stats()
        if "due today"  in t:                     return self.due_today()
        m = re.search(r"#?(\d+)", text)
        tid = int(m.group(1)) if m else 0
        if "complete" in t or "done" in t: return self.complete(tid)
        if "start"    in t:               return self.start(tid)
        if "block"    in t:               return self.block(tid)
        if "reopen"   in t:               return self.reopen(tid)
        if "delete"   in t:               return self.delete(tid)
        return "Unknown todo command."

    # ------------------------------------------------------------------ #
    # Public API — called by dispatcher
    # ------------------------------------------------------------------ #

    def add(self, title: str, priority: int = 2, tags: str = "",
            due: str = "", project: str = "") -> str:
        if not title.strip():
            return "Please provide a title for the todo."
        now = time.time()
        tid = self._db.insert(
            "INSERT INTO todos (created_at, updated_at, title, priority, tags, due, project) "
            "VALUES (?,?,?,?,?,?,?)",
            (now, now, title.strip(), max(1, min(4, int(priority))),
             tags.strip(), due.strip(), project.strip())
        )
        pri = _PRI_MAP.get(int(priority), "medium")
        return f"✓ Todo #{tid} added [{pri}]: {title.strip()}"

    def list_todos(self, status: str = "", tag: str = "", project: str = "") -> str:
        clauses, params = ["1"], []
        if status and status in _STATUS:
            clauses.append("status=?"); params.append(status)
        elif not status:
            clauses.append("status != 'done'")
        if tag:
            clauses.append("tags LIKE ?"); params.append(f"%{tag}%")
        if project:
            clauses.append("project=?"); params.append(project)
        rows = self._db.fetchall(
            f"SELECT id, title, status, priority, tags, due, project "
            f"FROM todos WHERE {' AND '.join(clauses)} ORDER BY priority DESC, created_at ASC",
            tuple(params)
        )
        if not rows:
            return "No todos found."
        lines = []
        for r in rows:
            pri  = _PRI_MAP.get(r["priority"], "?")
            due  = f" due:{r['due']}"   if r.get("due")     else ""
            proj = f" @{r['project']}" if r.get("project") else ""
            tags = f" #{r['tags']}"    if r.get("tags")    else ""
            lines.append(f"  #{r['id']:<3} [{r['status']:<11}] [{pri:<6}] {r['title']}{proj}{tags}{due}")
        return f"Todos ({len(rows)}):\n" + "\n".join(lines)

    def _change_status(self, tid: int, new_status: str) -> str:
        if not tid:
            return "Please provide a todo id."
        affected = self._db.execute(
            "UPDATE todos SET status=?, updated_at=? WHERE id=?",
            (new_status, time.time(), tid)
        ).rowcount
        return f"Todo #{tid} → {new_status}." if affected else f"Todo #{tid} not found."

    def complete(self, tid: int) -> str: return self._change_status(tid, "done")
    def start(self,    tid: int) -> str: return self._change_status(tid, "in_progress")
    def block(self,    tid: int) -> str: return self._change_status(tid, "blocked")
    def reopen(self,   tid: int) -> str: return self._change_status(tid, "active")

    def delete(self, tid: int) -> str:
        if not tid:
            return "Please provide a todo id."
        affected = self._db.execute("DELETE FROM todos WHERE id=?", (tid,)).rowcount
        return f"Todo #{tid} deleted." if affected else f"Todo #{tid} not found."

    def search(self, query: str) -> str:
        rows = self._db.fetchall(
            "SELECT id, title, status, priority FROM todos "
            "WHERE title LIKE ? OR tags LIKE ? OR project LIKE ? "
            "ORDER BY priority DESC",
            (f"%{query}%", f"%{query}%", f"%{query}%")
        )
        if not rows:
            return f"No todos matching '{query}'."
        lines = [f"  #{r['id']:<3} [{r['status']:<11}] {r['title']}" for r in rows]
        return f"Search results for '{query}':\n" + "\n".join(lines)

    def due_today(self) -> str:
        today = time.strftime("%Y-%m-%d")
        rows  = self._db.fetchall(
            "SELECT id, title, priority, project FROM todos "
            "WHERE due<=? AND status!='done' ORDER BY priority DESC",
            (today,)
        )
        if not rows:
            return "Nothing due today."
        lines = [f"  #{r['id']:<3} [{_PRI_MAP.get(r['priority'],'?'):<6}] {r['title']}" for r in rows]
        return f"Due today ({len(rows)}):\n" + "\n".join(lines)

    def stats(self) -> str:
        total = self._db.fetchone("SELECT COUNT(*) as n FROM todos") or {"n": 0}
        by_status = self._db.fetchall(
            "SELECT status, COUNT(*) as n FROM todos GROUP BY status ORDER BY n DESC"
        )
        lines = [f"  Total: {total['n']}"]
        for r in by_status:
            lines.append(f"  {r['status']:<14} {r['n']}")
        return "Todo stats:\n" + "\n".join(lines)

    def edit(self, todo_id: int, title: str = "", priority: int = 0,
             tags: str = "", due: str = "", project: str = "") -> str:
        if not todo_id:
            return "Please provide a todo id."
        sets, params = [], []
        if title:    sets.append("title=?");    params.append(title.strip())
        if priority: sets.append("priority=?"); params.append(max(1, min(4, priority)))
        if tags:     sets.append("tags=?");     params.append(tags.strip())
        if due:      sets.append("due=?");      params.append(due.strip())
        if project:  sets.append("project=?"); params.append(project.strip())
        if not sets:
            return "Nothing to update."
        sets.append("updated_at=?"); params.append(time.time())
        params.append(todo_id)
        self._db.execute(
            f"UPDATE todos SET {', '.join(sets)} WHERE id=?",
            tuple(params)
        )
        return f"Todo #{todo_id} updated."

    def _run_add(self, text: str) -> str:
        """Keyword-fallback parser for raw 'add todo ...' text."""
        title = re.sub(r"(add todo|add task)", "", text, flags=re.I).strip()
        pri   = 2
        if "!high"   in title or "high priority"   in title: pri = 3
        if "!urgent" in title or "urgent"           in title: pri = 4
        if "!low"    in title or "low priority"     in title: pri = 1
        title = re.sub(r"!(?:high|low|urgent|medium)", "", title).strip()
        return self.add(title, priority=pri)
