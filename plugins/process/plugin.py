"""Process manager plugin — list, find, kill processes."""

import subprocess
import platform
from plugins.base import PluginBase

_INTENTS = {
    ("list process", "ps ", "running process", "what's running") : "_list",
    ("kill ", "stop process", "end process")                     : "_kill",
    ("find process", "is running", "process info")               : "_find",
}


class Plugin(PluginBase):
    priority = 12

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text)
        return "Process plugin: could not parse intent."

    def _list(self, text: str) -> str:
        try:
            import psutil
            procs = sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                           key=lambda p: p.info["cpu_percent"] or 0, reverse=True)
            lines = [f"{'PID':>7}  {'CPU%':>5}  {'MEM%':>5}  NAME"]
            for p in procs[:20]:
                i = p.info
                lines.append(f"{i['pid']:>7}  {i['cpu_percent'] or 0:>5.1f}  {i['memory_percent'] or 0:>5.1f}  {i['name']}")
            return "\n".join(lines)
        except ImportError:
            return self._list_fallback()

    def _list_fallback(self) -> str:
        cmd = ["tasklist"] if platform.system() == "Windows" else ["ps", "aux", "--sort=-%cpu"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            lines = r.stdout.strip().splitlines()
            return "\n".join(lines[:25])
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
            target = int(arg) if arg.isdigit() else None
            killed = []
            for p in psutil.process_iter(["pid", "name"]):
                if (target and p.pid == target) or (not target and arg.lower() in p.info["name"].lower()):
                    p.terminate()
                    killed.append(f"{p.info['name']} (pid {p.pid})")
            return f"Terminated: {', '.join(killed)}" if killed else f"No process found matching '{arg}'"
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
            matches = [p.info for p in psutil.process_iter(["pid", "name", "status", "cpu_percent"])
                       if arg.lower() in p.info["name"].lower()]
            if not matches:
                return f"No process found matching '{arg}'"
            return "\n".join(f"pid={m['pid']}  status={m['status']}  cpu={m['cpu_percent']}%  {m['name']}" for m in matches)
        except ImportError:
            return "Install psutil: pip install psutil"
