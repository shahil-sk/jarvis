"""Notes plugin — save, list, search, delete notes across sessions."""

import time
from plugins.base import PluginBase

_INTENTS = {
    ("save note", "remember this", "note down", "add note") : "_save",
    ("show notes", "list notes", "my notes", "all notes")   : "_list",
    ("search note", "find note", "notes about")              : "_search",
    ("delete note", "remove note")                           : "_delete",
    ("recall", "what did i say", "history")                  : "_history",
    ("forget everything", "clear history", "wipe memory")    : "_forget",
}


class Plugin(PluginBase):
    priority = 25

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text, memory)
        return "Notes: could not parse intent."

    def _save(self, text: str, memory) -> str:
        for trigger in ("save note ", "remember this ", "note down ", "add note "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                content = text[idx:].strip()
                break
        else:
            content = text.strip()

        # Extract optional #tag
        tag = ""
        words = content.split()
        tags = [w[1:] for w in words if w.startswith("#")]
        if tags:
            tag = tags[0]
            content = " ".join(w for w in words if not w.startswith("#")).strip()

        nid = memory.save_note(content, tag)
        return f"Note #{nid} saved{'  [#' + tag + ']' if tag else ''}:  {content}"

    def _list(self, text: str, memory) -> str:
        # check for tag filter
        tag = ""
        t = text.lower()
        if "#" in t:
            idx = t.index("#")
            tag = text[idx+1:].split()[0]
        notes = memory.get_notes(tag=tag, limit=15)
        if not notes:
            return "No notes found."
        lines = []
        for n in notes:
            ts = time.strftime("%d %b %H:%M", time.localtime(n["ts"]))
            tag_str = f" [#{n['tag']}]" if n["tag"] else ""
            lines.append(f"#{n['id']} {ts}{tag_str}  {n['content']}")
        return "\n".join(lines)

    def _search(self, text: str, memory) -> str:
        for trigger in ("search note ", "find note ", "notes about "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                query = text[idx:].strip().lower()
                break
        else:
            return "Usage: search note <query>"
        notes = memory.get_notes(limit=100)
        results = [n for n in notes if query in n["content"].lower()]
        if not results:
            return f"No notes matching '{query}'"
        lines = []
        for n in results[:10]:
            ts = time.strftime("%d %b %H:%M", time.localtime(n["ts"]))
            lines.append(f"#{n['id']} {ts}  {n['content']}")
        return "\n".join(lines)

    def _delete(self, text: str, memory) -> str:
        for trigger in ("delete note ", "remove note "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip().lstrip("#")
                break
        else:
            return "Usage: delete note <id>"
        if not arg.isdigit():
            return "Usage: delete note <id>  (numeric id)"
        ok = memory.delete_note(int(arg))
        return f"Note #{arg} deleted." if ok else f"Could not delete note #{arg}."

    def _history(self, text: str, memory) -> str:
        entries = memory.recall(n=10)
        if not entries:
            return "No history yet."
        lines = []
        for e in entries:
            ts = time.strftime("%d %b %H:%M", time.localtime(e["ts"]))
            prefix = "You" if e["role"] == "user" else "Jarvis"
            lines.append(f"{ts}  [{prefix}] {e['content'][:120]}")
        return "\n".join(lines)

    def _forget(self, text: str, memory) -> str:
        ok = memory.forget()
        return "Memory wiped." if ok else "[error] Could not wipe memory."
