"""Filesystem plugin — find, read, list, move, delete files."""

import os
import shutil
import glob
from plugins.base import PluginBase

_INTENTS = {
    ("find ", "search file", "locate ")        : "_find",
    ("read ", "show file", "cat ", "open file") : "_read",
    ("list ", "ls ", "dir ")                    : "_list",
    ("move ", "rename ")                        : "_move",
    ("delete file", "remove file", "rm file")   : "_delete",
    ("mkdir ", "make dir", "create folder")     : "_mkdir",
    ("pwd", "current dir", "where am i")        : "_pwd",
}


class Plugin(PluginBase):
    priority = 15

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text)
        return "Filesystem: could not parse intent."

    def _find(self, text: str) -> str:
        pattern = self._extract_arg(text, ("find ", "locate ", "search file "))
        if not pattern:
            return "Usage: find <filename or pattern>"
        results = glob.glob(f"**/{pattern}", recursive=True)
        if not results:
            return f"No files matching '{pattern}' found under {os.getcwd()}"
        return "\n".join(results[:20]) + ("\n..." if len(results) > 20 else "")

    def _read(self, text: str) -> str:
        path = self._extract_arg(text, ("read ", "cat ", "show file ", "open file "))
        if not path or not os.path.isfile(path):
            return f"File not found: '{path}'"
        size = os.path.getsize(path)
        if size > 50_000:
            return f"File too large to display ({size} bytes). Use 'run cat {path}' for full output."
        try:
            with open(path, "r", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"[error] {e}"

    def _list(self, text: str) -> str:
        path = self._extract_arg(text, ("list ", "ls ", "dir ")) or "."
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return f"Not a directory: '{path}'"
        entries = os.listdir(path)
        dirs  = sorted(e + "/" for e in entries if os.path.isdir(os.path.join(path, e)))
        files = sorted(e for e in entries if os.path.isfile(os.path.join(path, e)))
        return f"{path}\n" + "\n".join(dirs + files) or "(empty)"

    def _move(self, text: str) -> str:
        arg = self._extract_arg(text, ("move ", "rename "))
        parts = arg.split(" to ") if " to " in (arg or "") else []
        if len(parts) != 2:
            return "Usage: move <src> to <dest>"
        src, dst = parts[0].strip(), parts[1].strip()
        if not os.path.exists(src):
            return f"Source not found: '{src}'"
        shutil.move(src, dst)
        return f"Moved '{src}' -> '{dst}'"

    def _delete(self, text: str) -> str:
        path = self._extract_arg(text, ("delete file ", "remove file ", "rm file "))
        if not path or not os.path.exists(path):
            return f"Not found: '{path}'"
        if os.path.isdir(path):
            return "Use 'run rm -r <dir>' for directories (safety check)."
        os.remove(path)
        return f"Deleted '{path}'"

    def _mkdir(self, text: str) -> str:
        path = self._extract_arg(text, ("mkdir ", "make dir ", "create folder "))
        if not path:
            return "Usage: mkdir <path>"
        os.makedirs(path, exist_ok=True)
        return f"Created directory '{path}'"

    def _pwd(self, text: str) -> str:
        return os.getcwd()

    @staticmethod
    def _extract_arg(text: str, triggers: tuple) -> str:
        t = text.strip()
        for trigger in triggers:
            if trigger.lower() in t.lower():
                idx = t.lower().index(trigger.lower()) + len(trigger)
                return t[idx:].strip()
        return ""
