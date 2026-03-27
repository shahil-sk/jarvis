"""System plugin — shell commands, stats, open apps, uptime."""

import os
import time
import platform
import subprocess
import shlex
from plugins.base import PluginBase

_START_TIME = time.time()

# intent keywords -> handler method name
_INTENTS = {
    ("cpu", "ram", "memory", "disk", "stats", "usage"): "_stats",
    ("uptime",): "_uptime",
    ("run ", "exec ", "shell ", "$ "): "_shell",
    ("open ", "launch ", "start "): "_open",
    ("os", "system info", "platform"): "_sysinfo",
}


class Plugin(PluginBase):
    priority = 10  # high priority — runs before LLM

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text)
        return "System plugin matched but could not parse intent."

    # ------------------------------------------------------------------ #

    def _stats(self, text: str) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return (
                f"CPU: {cpu}%  |  "
                f"RAM: {ram.used // 1024**2}MB / {ram.total // 1024**2}MB ({ram.percent}%)  |  "
                f"Disk: {disk.used // 1024**3}GB / {disk.total // 1024**3}GB ({disk.percent}%)"
            )
        except ImportError:
            return "Install psutil for stats: pip install psutil"

    def _uptime(self, text: str) -> str:
        secs = int(time.time() - _START_TIME)
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return f"Jarvis uptime: {h}h {m}m {s}s"

    def _sysinfo(self, text: str) -> str:
        return (
            f"OS: {platform.system()} {platform.release()} | "
            f"Machine: {platform.machine()} | "
            f"Python: {platform.python_version()}"
        )

    def _shell(self, text: str) -> str:
        """Run a shell command. Strips trigger keywords first."""
        for trigger in ("run ", "exec ", "shell ", "$ "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                cmd = text[idx:].strip()
                break
        else:
            return "No command found. Usage: run <command>"

        if not cmd:
            return "Empty command."

        # Basic safeguard: block destructive patterns
        blocked = ("rm -rf /", "mkfs", "> /dev/sd", "dd if=")
        if any(b in cmd for b in blocked):
            return "[blocked] That command is too dangerous to run."

        try:
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True, text=True, timeout=10
            )
            out = (result.stdout + result.stderr).strip()
            return out[:1000] if out else f"[exit {result.returncode}]"
        except subprocess.TimeoutExpired:
            return "[timeout] Command took too long (>10s)."
        except FileNotFoundError:
            return f"[error] Command not found: {cmd.split()[0]}"
        except Exception as e:
            return f"[error] {e}"

    def _open(self, text: str) -> str:
        """Open an application or file."""
        for trigger in ("open ", "launch ", "start "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                target = text[idx:].strip()
                break
        else:
            return "Usage: open <app or file>"

        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", target])
            elif system == "Windows":
                os.startfile(target)
            else:  # Linux
                subprocess.Popen(["xdg-open", target])
            return f"Opening '{target}'..."
        except Exception as e:
            return f"[error] {e}"
