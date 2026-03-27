"""Notes plugin v2 — migrated to core.db (WAL, migrations, no raw sqlite3).

Notes are stored in the shared memory.db via core.db.DB.
The plugin delegates to memory.save_note / memory.get_notes for all
SQLite access, so there's a single source of truth for the notes table.
"""

import time
import re
from plugins.base import PluginBase


class Plugin(PluginBase):
    priority = 40

    def matches(self, text: str) -> bool:
        return any(kw in text.lower() for kw in
                   ("save note", "remember this", "show notes", "list notes",
                    "search note", "delete note", "forget notes", "note history"))

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(k in t for k in ("save note", "remember this", "note:")): return self._save(text, memory)
        if any(k in t for k in ("show notes", "list notes")): return self._list(text, memory)
        if "search note" in t:  return self._search(text, memory)
        if "delete note" in t:  return self._delete(text, memory)
        if "forget notes" in t: return self._forget(text, memory)
        if "note history" in t: return self._history(text, memory)
        return "Unknown notes command."

    # ------------------------------------------------------------------ #
    # These methods are also called directly by dispatcher
    # ------------------------------------------------------------------ #

    def _save(self, text: str, memory) -> str:
        # Strip trigger phrase, extract optional #tag
        content = re.sub(r"(save note|remember this|note:)", "", text, flags=re.I).strip()
        tag_m   = re.search(r"#(\w+)", content)
        tag     = tag_m.group(1).lower() if tag_m else ""
        content = re.sub(r"#\w+", "", content).strip()
        if not content:
            return "Nothing to save — provide content after 'save note'."
        nid = memory.save_note(content, tag=tag)
        tag_str = f" [#{tag}]" if tag else ""
        return f"✓ Note #{nid} saved{tag_str}: {content}"

    def _list(self, text: str, memory) -> str:
        tag_m = re.search(r"#(\w+)", text)
        tag   = tag_m.group(1).lower() if tag_m else ""
        notes = memory.get_notes(tag=tag, limit=20)
        if not notes:
            label = f" tagged #{tag}" if tag else ""
            return f"No notes{label}."
        lines = []
        for n in notes:
            when = time.strftime("%d %b", time.localtime(n["ts"]))
            tag_s = f" [#{n['tag']}]" if n.get("tag") else ""
            lines.append(f"  #{n['id']:<4} {when}  {tag_s}  {n['content']}")
        return f"Notes ({len(notes)}):\n" + "\n".join(lines)

    def _search(self, text: str, memory) -> str:
        query = re.sub(r"search note[s]?", "", text, flags=re.I).strip()
        if not query:
            return "Provide a search term: search notes <query>"
        notes = memory.get_notes(search=query, limit=20)
        if not notes:
            return f"No notes matching '{query}'."
        lines = [f"  #{n['id']:<4} {n['content']}" for n in notes]
        return f"Notes matching '{query}' ({len(notes)}):\n" + "\n".join(lines)

    def _delete(self, text: str, memory) -> str:
        m = re.search(r"#?(\d+)", text)
        if not m:
            return "Usage: delete note <id>"
        nid = int(m.group(1))
        ok  = memory.delete_note(nid)
        return f"Note #{nid} deleted." if ok else f"Note #{nid} not found."

    def _history(self, text: str, memory) -> str:
        notes = memory.get_notes(limit=20)
        return self._list("", memory) if notes else "No notes yet."

    def _forget(self, text: str, memory) -> str:
        """Wipe ALL notes — requires explicit confirmation phrase."""
        if "confirm" not in text.lower():
            return ("This will delete ALL notes. "
                    "Type 'forget notes confirm' to proceed.")
        from core.db import DB
        try:
            DB().execute("DELETE FROM notes")
            return "✓ All notes deleted."
        except Exception as exc:
            return f"Error deleting notes: {exc}"
