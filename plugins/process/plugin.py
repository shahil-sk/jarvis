"""Process plugin — list, find, kill, suspend, resume, top, tree."""

import subprocess
import platform
from plugins.base import PluginBase, PluginCapability


class Plugin(PluginBase):
    priority = 12

    capabilities = [
        PluginCapability(
            intent="process.list",
            description="List running processes sorted by CPU usage",
            args={},
            trigger_template="list processes",
            examples=[
                ("what is running", {}),
                ("show running processes", {}),
                ("ps aux", {}),
            ],
        ),
        PluginCapability(
            intent="process.kill",
            description="Kill a process by name or PID",
            args={"target": "str"},
            trigger_template="kill {target}",
            examples=[
                ("kill chrome", {"target": "chrome"}),
                ("stop process 1234", {"target": "1234"}),
                ("end process firefox", {"target": "firefox"}),
            ],
        ),
        PluginCapability(
            intent="process.find",
            description="Find a process by name and show its info",
            args={"name": "str"},
            trigger_template="find process {name}",
            examples=[
                ("is nginx running", {"name": "nginx"}),
                ("find process python", {"name": "python"}),
            ],
        ),
        PluginCapability(
            intent="process.top",
            description="Show top N processes by CPU or memory",
            args={"by": "str?", "limit": "int?"},
            trigger_template="top processes",
            examples=[
                ("show top 10 processes by memory", {"by": "memory", "limit": 10}),
                ("top 5 cpu processes", {"by": "cpu", "limit": 5}),
            ],
        ),
        PluginCapability(
            intent="process.suspend",
            description="Suspend (pause) a running process",
            args={"target": "str"},
            trigger_template="suspend process {target}",
            examples=[("suspend firefox", {"target": "firefox"})],
        ),
        PluginCapability(
            intent="process.resume",
            description="Resume a suspended process",
            args={"target": "str"},
            trigger_template="resume process {target}",
            examples=[("resume firefox", {"target": "firefox"})],
        ),
    ]

    def matches(self, text: str) -> bool:
        keywords = (
            "list process", "ps ", "running process", "what's running",
            "what is running", "kill ", "stop process", "end process",
            "find process", "is running", "process info", "top process",
            "suspend ", "resume process",
        )
        t = text.lower()
        return any(kw in t for kw in keywords)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(k in t for k in ("list process", "ps ", "running process", "what is running", "what's running")):
            return self._list()
        if any(k in t for k in ("kill ", "stop process", "end process")):
            return self._kill(text)
        if any(k in t for k in ("find process", "is running", "process info")):
            return self._find(text)
        if "top" in t and "process" in t:
            return self._top(text)
        if "suspend" in t:
            return self._suspend(text)
        if "resume" in t:
            return self._resume(text)
        return "Process: could not parse intent."

    def run_intent(self, intent: str, args: dict) -> str:
        dispatch = {
            "process.list"   : lambda: self._list(),
            "process.kill"   : lambda: self._kill(f"kill {args.get('target', '')}"),
            "process.find"   : lambda: self._find(f"find process {args.get('name', '')}"),
            "process.top"    : lambda: self._top_direct(args.get('by', 'cpu'), int(args.get('limit', 10))),
            "process.suspend": lambda: self._suspend(f"suspend {args.get('target', '')}"),
            "process.resume" : lambda: self._resume(f"resume {args.get('target', '')}"),
        }
        fn = dispatch.get(intent)
        return fn() if fn else f"Unknown process intent: {intent}"

    def _list(self) -> str:
        try:
            import psutil
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]),
                key=lambda p: p.info.get("cpu_percent") or 0, reverse=True
            )
            lines = [f"{'PID':>7}  {'CPU%':>5}  {'MEM%':>5}  {'STATUS':<10}  NAME"]
            lines.append("-" * 55)
            for p in procs[:25]:
                i = p.info
                lines.append(
                    f"{i['pid']:>7}  {i['cpu_percent'] or 0:>5.1f}  "
                    f"{i['memory_percent'] or 0:>5.1f}  "
                    f"{i['status']:<10}  {i['name']}"
                )
            return "\n".join(lines)
        except ImportError:
            return self._list_fallback()

    def _list_fallback(self) -> str:
        cmd = ["tasklist"] if platform.system() == "Windows" else ["ps", "aux", "--sort=-%cpu"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return "\n".join(r.stdout.strip().splitlines()[:25])
        except Exception as e:
            return f"[error] {e}"

    def _kill(self, text: str) -> str:
        arg = ""
        for trigger in ("kill ", "stop process ", "end process "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip()
                break
        if not arg:
            return "Usage: kill <pid or process name>"
        try:
            import psutil
            target  = int(arg) if arg.isdigit() else None
            killed  = []
            for p in psutil.process_iter(["pid", "name"]):
                match = (target and p.pid == target) or (
                    not target and arg.lower() in p.info["name"].lower()
                )
                if match:
                    p.terminate()
                    killed.append(f"{p.info['name']} (pid {p.pid})")
            return f"Terminated: {', '.join(killed)}" if killed else f"No process matching '{arg}'"
        except ImportError:
            return "Install psutil: pip install psutil"
        except Exception as e:
            return f"[error] {e}"

    def _find(self, text: str) -> str:
        arg = ""
        for trigger in ("find process ", "is running ", "process info "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip()
                break
        if not arg:
            return "Usage: find process <name>"
        try:
            import psutil
            found = []
            for p in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_percent", "cmdline"]):
                if arg.lower() in p.info["name"].lower():
                    cmd = " ".join(p.info.get("cmdline") or [])[:80]
                    found.append(
                        f"pid={p.info['pid']}  status={p.info['status']}  "
                        f"cpu={p.info['cpu_percent'] or 0:.1f}%  "
                        f"mem={p.info['memory_percent'] or 0:.1f}%  "
                        f"{p.info['name']}\n  cmd: {cmd}"
                    )
            if not found:
                return f"No process found matching '{arg}'"
            return "\n".join(found)
        except ImportError:
            return "Install psutil: pip install psutil"

    def _top_direct(self, by: str = "cpu", limit: int = 10) -> str:
        try:
            import psutil
            key = "memory_percent" if "mem" in by.lower() else "cpu_percent"
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get(key) or 0, reverse=True
            )[:limit]
            lines = [f"Top {limit} by {by.upper()}:", f"{'PID':>7}  {'CPU%':>5}  {'MEM%':>5}  NAME"]
            for p in procs:
                i = p.info
                lines.append(f"{i['pid']:>7}  {i['cpu_percent'] or 0:>5.1f}  {i['memory_percent'] or 0:>5.1f}  {i['name']}")
            return "\n".join(lines)
        except ImportError:
            return "Install psutil: pip install psutil"

    def _top(self, text: str) -> str:
        t = text.lower()
        by    = "memory" if "mem" in t else "cpu"
        limit = 10
        import re
        m = re.search(r"top\s+(\d+)", t)
        if m:
            limit = int(m.group(1))
        return self._top_direct(by, limit)

    def _suspend(self, text: str) -> str:
        arg = ""
        for trigger in ("suspend ", "pause process "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip()
                break
        if not arg:
            return "Usage: suspend <name or pid>"
        try:
            import psutil
            for p in psutil.process_iter(["pid", "name"]):
                if arg.lower() in p.info["name"].lower() or str(p.pid) == arg:
                    p.suspend()
                    return f"Suspended {p.info['name']} (pid {p.pid})"
            return f"No process matching '{arg}'"
        except ImportError:
            return "Install psutil: pip install psutil"

    def _resume(self, text: str) -> str:
        arg = ""
        for trigger in ("resume ", "resume process "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip()
                break
        if not arg:
            return "Usage: resume <name or pid>"
        try:
            import psutil
            for p in psutil.process_iter(["pid", "name"]):
                if arg.lower() in p.info["name"].lower() or str(p.pid) == arg:
                    p.resume()
                    return f"Resumed {p.info['name']} (pid {p.pid})"
            return f"No process matching '{arg}'"
        except ImportError:
            return "Install psutil: pip install psutil"
