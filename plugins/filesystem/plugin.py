"""Filesystem plugin — find, read, write, list, move, copy, delete, stat, tree."""

import os
import shutil
import glob
import time
from plugins.base import PluginBase, PluginCapability


class Plugin(PluginBase):
    priority = 15

    capabilities = [
        PluginCapability(
            intent="fs.find",
            description="Find files matching a name or glob pattern",
            args={"pattern": "str"},
            trigger_template="find {pattern}",
            examples=[
                ("find all py files", {"pattern": "*.py"}),
                ("locate config.yaml", {"pattern": "config.yaml"}),
            ],
        ),
        PluginCapability(
            intent="fs.read",
            description="Read and show the content of a file",
            args={"path": "str"},
            trigger_template="read {path}",
            examples=[
                ("show me requirements.txt", {"path": "requirements.txt"}),
                ("read /etc/hosts", {"path": "/etc/hosts"}),
            ],
        ),
        PluginCapability(
            intent="fs.write",
            description="Write or append content to a file",
            args={"path": "str", "content": "str", "mode": "str?"},
            trigger_template="write {path}",
            examples=[
                ("write hello world to test.txt", {"path": "test.txt", "content": "hello world"}),
            ],
        ),
        PluginCapability(
            intent="fs.list",
            description="List directory contents",
            args={"path": "str?"},
            trigger_template="list {path}",
            examples=[
                ("list current directory", {"path": "."}),
                ("ls /etc", {"path": "/etc"}),
            ],
        ),
        PluginCapability(
            intent="fs.move",
            description="Move or rename a file or directory",
            args={"src": "str", "dst": "str"},
            trigger_template="move {src} to {dst}",
            examples=[
                ("move old.txt to new.txt", {"src": "old.txt", "dst": "new.txt"}),
            ],
        ),
        PluginCapability(
            intent="fs.copy",
            description="Copy a file or directory",
            args={"src": "str", "dst": "str"},
            trigger_template="copy {src} to {dst}",
            examples=[
                ("copy config.yaml to config.bak", {"src": "config.yaml", "dst": "config.bak"}),
            ],
        ),
        PluginCapability(
            intent="fs.delete",
            description="Delete a file",
            args={"path": "str"},
            trigger_template="delete file {path}",
            examples=[
                ("delete old.log", {"path": "old.log"}),
                ("remove file test.txt", {"path": "test.txt"}),
            ],
        ),
        PluginCapability(
            intent="fs.mkdir",
            description="Create a directory (including parents)",
            args={"path": "str"},
            trigger_template="mkdir {path}",
            examples=[
                ("create folder logs", {"path": "logs"}),
                ("mkdir /tmp/test", {"path": "/tmp/test"}),
            ],
        ),
        PluginCapability(
            intent="fs.pwd",
            description="Show current working directory",
            args={},
            trigger_template="current directory",
            examples=[("where am i", {}), ("show current directory", {})],
        ),
        PluginCapability(
            intent="fs.stat",
            description="Show size, permissions, and timestamps of a file",
            args={"path": "str"},
            trigger_template="stat {path}",
            examples=[
                ("show info about main.py", {"path": "main.py"}),
                ("file stat config.yaml", {"path": "config.yaml"}),
            ],
        ),
        PluginCapability(
            intent="fs.tree",
            description="Show a directory tree",
            args={"path": "str?", "depth": "int?"},
            trigger_template="tree {path}",
            examples=[
                ("show directory tree", {"path": "."}),
                ("tree plugins", {"path": "plugins"}),
            ],
        ),
        PluginCapability(
            intent="fs.diskusage",
            description="Show disk usage of a directory",
            args={"path": "str?"},
            trigger_template="disk usage {path}",
            examples=[
                ("disk usage of /var", {"path": "/var"}),
                ("how big is the plugins folder", {"path": "plugins"}),
            ],
        ),
    ]

    def matches(self, text: str) -> bool:
        keywords = (
            "find ", "search file", "locate ", "read ", "show file",
            "cat ", "open file", "list ", "ls ", "dir ", "move ",
            "rename ", "delete file", "remove file", "rm file",
            "mkdir ", "make dir", "create folder", "pwd", "current dir",
            "where am i", "copy ", "stat ", "tree ", "disk usage", "write ",
        )
        t = text.lower()
        return any(kw in t for kw in keywords)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(k in t for k in ("find ", "search file", "locate ")):
            return self._find(text)
        if any(k in t for k in ("read ", "cat ", "show file", "open file")):
            return self._read(text)
        if any(k in t for k in ("list ", "ls ", "dir ")):
            return self._list(text)
        if any(k in t for k in ("move ", "rename ")):
            return self._move(text)
        if any(k in t for k in ("copy ",)):
            return self._copy(text)
        if any(k in t for k in ("delete file", "remove file", "rm file")):
            return self._delete(text)
        if any(k in t for k in ("mkdir ", "make dir", "create folder")):
            return self._mkdir(text)
        if any(k in t for k in ("pwd", "current dir", "where am i")):
            return self._pwd()
        if "stat " in t:
            return self._stat(text)
        if "tree" in t:
            return self._tree(text)
        if "disk usage" in t:
            return self._diskusage(text)
        if "write " in t:
            return self._write(text)
        return "Filesystem: could not parse intent."

    def run_intent(self, intent: str, args: dict) -> str:
        dispatch = {
            "fs.find"     : lambda: self._find(f"find {args.get('pattern', '')}"),
            "fs.read"     : lambda: self._read(f"read {args.get('path', '')}"),
            "fs.write"    : lambda: self._write_direct(args.get('path', ''), args.get('content', ''), args.get('mode', 'w')),
            "fs.list"     : lambda: self._list(f"list {args.get('path', '.')}"),
            "fs.move"     : lambda: self._move(f"move {args.get('src', '')} to {args.get('dst', '')}"),
            "fs.copy"     : lambda: self._copy(f"copy {args.get('src', '')} to {args.get('dst', '')}"),
            "fs.delete"   : lambda: self._delete(f"delete file {args.get('path', '')}"),
            "fs.mkdir"    : lambda: self._mkdir(f"mkdir {args.get('path', '')}"),
            "fs.pwd"      : lambda: self._pwd(),
            "fs.stat"     : lambda: self._stat(f"stat {args.get('path', '')}"),
            "fs.tree"     : lambda: self._tree_direct(args.get('path', '.'), int(args.get('depth', 3))),
            "fs.diskusage": lambda: self._diskusage(f"disk usage {args.get('path', '.')}"),
        }
        fn = dispatch.get(intent)
        return fn() if fn else f"Unknown fs intent: {intent}"

    def _find(self, text: str) -> str:
        pattern = _arg(text, ("find ", "locate ", "search file "))
        if not pattern:
            return "Usage: find <pattern>"
        results = glob.glob(f"**/{pattern}", recursive=True)
        if not results:
            return f"No files matching '{pattern}' under {os.getcwd()}"
        out = "\n".join(sorted(results)[:30])
        return out + ("\n..." if len(results) > 30 else "")

    def _read(self, text: str) -> str:
        path = _arg(text, ("read ", "cat ", "show file ", "open file "))
        path = os.path.expanduser(path)
        if not path or not os.path.isfile(path):
            return f"File not found: '{path}'"
        size = os.path.getsize(path)
        if size > 100_000:
            return f"File too large ({size // 1024}KB). Use: run cat {path}"
        try:
            with open(path, "r", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"[error] {e}"

    def _write_direct(self, path: str, content: str, mode: str = "w") -> str:
        if not path:
            return "No path specified."
        path = os.path.expanduser(path)
        mode = "a" if mode == "append" else "w"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, mode) as f:
                f.write(content)
            action = "Appended" if mode == "a" else "Written"
            return f"{action} to '{path}'"
        except Exception as e:
            return f"[error] {e}"

    def _write(self, text: str) -> str:
        # Simple parser: write <content> to <path>
        t = text
        if " to " in t:
            parts = t.split(" to ", 1)
            content = _arg(parts[0], ("write ",)).strip()
            path    = parts[1].strip()
        else:
            return "Usage: write <content> to <path>"
        return self._write_direct(path, content + "\n")

    def _list(self, text: str) -> str:
        path = os.path.expanduser(_arg(text, ("list ", "ls ", "dir ")) or ".")
        if not os.path.isdir(path):
            return f"Not a directory: '{path}'"
        entries = sorted(os.listdir(path))
        dirs  = [e + "/" for e in entries if os.path.isdir(os.path.join(path, e))]
        files = [e          for e in entries if os.path.isfile(os.path.join(path, e))]
        total = len(dirs) + len(files)
        header = f"{path}  ({len(dirs)} dirs, {len(files)} files)"
        return header + "\n" + "\n".join(dirs + files)

    def _move(self, text: str) -> str:
        arg = _arg(text, ("move ", "rename "))
        parts = arg.split(" to ", 1) if " to " in (arg or "") else []
        if len(parts) != 2:
            return "Usage: move <src> to <dest>"
        src, dst = os.path.expanduser(parts[0].strip()), os.path.expanduser(parts[1].strip())
        if not os.path.exists(src):
            return f"Source not found: '{src}'"
        shutil.move(src, dst)
        return f"Moved '{src}' -> '{dst}'"

    def _copy(self, text: str) -> str:
        arg = _arg(text, ("copy ",))
        parts = arg.split(" to ", 1) if " to " in (arg or "") else []
        if len(parts) != 2:
            return "Usage: copy <src> to <dest>"
        src, dst = os.path.expanduser(parts[0].strip()), os.path.expanduser(parts[1].strip())
        if not os.path.exists(src):
            return f"Source not found: '{src}'"
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return f"Copied '{src}' -> '{dst}'"
        except Exception as e:
            return f"[error] {e}"

    def _delete(self, text: str) -> str:
        path = os.path.expanduser(_arg(text, ("delete file ", "remove file ", "rm file ", "delete ")))
        if not path or not os.path.exists(path):
            return f"Not found: '{path}'"
        if os.path.isdir(path):
            return "For directories use: run rm -r <dir>"
        os.remove(path)
        return f"Deleted '{path}'"

    def _mkdir(self, text: str) -> str:
        path = os.path.expanduser(_arg(text, ("mkdir ", "make dir ", "create folder ")))
        if not path:
            return "Usage: mkdir <path>"
        os.makedirs(path, exist_ok=True)
        return f"Created directory '{path}'"

    def _pwd(self) -> str:
        return os.getcwd()

    def _stat(self, text: str) -> str:
        path = os.path.expanduser(_arg(text, ("stat ", "file stat ", "info about ", "show info about ")))
        if not path or not os.path.exists(path):
            return f"Not found: '{path}'"
        st  = os.stat(path)
        return "\n".join([
            f"Path  : {os.path.abspath(path)}",
            f"Size  : {st.st_size:,} bytes  ({st.st_size // 1024}KB)",
            f"Mode  : {oct(st.st_mode)}",
            f"Inode : {st.st_ino}",
            f"Mtime : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}",
            f"Ctime : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_ctime))}",
        ])

    def _tree_direct(self, path: str = ".", depth: int = 3) -> str:
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return f"Not a directory: '{path}'"
        lines = [path]
        _walk_tree(path, "", depth, 0, lines)
        if len(lines) > 100:
            lines = lines[:100]
            lines.append("... (truncated)")
        return "\n".join(lines)

    def _tree(self, text: str) -> str:
        p = _arg(text, ("tree ",)) or "."
        return self._tree_direct(p)

    def _diskusage(self, text: str) -> str:
        path = os.path.expanduser(_arg(text, ("disk usage ", "how big is the ", "how big is ")) or ".")
        if not os.path.exists(path):
            return f"Not found: '{path}'"
        try:
            r = __import__("subprocess").run(
                ["du", "-sh", path], capture_output=True, text=True, timeout=15
            )
            return r.stdout.strip() or f"du error: {r.stderr.strip()}"
        except Exception:
            total = sum(
                os.path.getsize(os.path.join(root, f))
                for root, _, files in os.walk(path)
                for f in files
                if not os.path.islink(os.path.join(root, f))
            )
            return f"{path}: {total // 1024 // 1024}MB ({total:,} bytes)"


def _arg(text: str, triggers: tuple) -> str:
    for t in triggers:
        if t.lower() in text.lower():
            idx = text.lower().index(t.lower()) + len(t)
            return text[idx:].strip()
    return ""


def _walk_tree(path, prefix, max_depth, depth, lines):
    if depth >= max_depth:
        return
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return
    for i, entry in enumerate(entries):
        is_last  = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        full = os.path.join(path, entry)
        lines.append(prefix + connector + entry + ("/" if os.path.isdir(full) else ""))
        if os.path.isdir(full):
            ext = "    " if is_last else "│   "
            _walk_tree(full, prefix + ext, max_depth, depth + 1, lines)
