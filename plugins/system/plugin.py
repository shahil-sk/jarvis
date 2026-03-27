"""System plugin — shell commands, stats, open apps, uptime."""

import os
import time
import platform
import subprocess
import shlex
from plugins.base import PluginBase

_START_TIME = time.time()

_INTENTS = {
    ("cpu", "ram", "memory", "disk", "stats", "usage")  : "_stats",
    ("uptime",)                                          : "_uptime",
    ("run ", "exec ", "shell ", "$ ")                    : "_shell",
    ("open ", "launch ", "start ")                       : "_open",
    ("os ", "system info", "platform")                   : "_sysinfo",
    ("env ", "environment variable", "getenv")           : "_env",
    ("set env ", "export ")                              : "_setenv",
}


class Plugin(PluginBase):
    priority = 10

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text)
        return "System plugin matched but could not parse intent."

    def _stats(self, text: str) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return (
                f"CPU : {cpu}%\n"
                f"RAM : {ram.used // 1024**2}MB / {ram.total // 1024**2}MB ({ram.percent}%)\n"
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
            f"OS     : {platform.system()} {platform.release()}\n"
            f"Machine: {platform.machine()}\n"
            f"Python : {platform.python_version()}\n"
            f"CWD    : {os.getcwd()}"
        )

    def _env(self, text: str) -> str:
        key = ""
        for trigger in ("env ", "getenv ", "environment variable "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                key = text[idx:].strip()
                break
        if not key:
            # list all
            lines = [f"{k}={v}" for k, v in list(os.environ.items())[:30]]
            return "\n".join(lines)
        val = os.environ.get(key)
        return f"{key}={val}" if val else f"{key} is not set"

    def _setenv(self, text: str) -> str:
        for trigger in ("set env ", "export "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip()
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    os.environ[k.strip()] = v.strip()
                    return f"Set {k.strip()}={v.strip()}"
        return "Usage: set env KEY=VALUE"

    def _shell(self, text: str) -> str:
        for trigger in ("run ", "exec ", "shell ", "$ "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                cmd = text[idx:].strip()
                break
        else:
            return "No command found."
        if not cmd:
            return "Empty command."
        blocked = ("rm -rf /", "mkfs", "> /dev/sd", "dd if=")
        if any(b in cmd for b in blocked):
            return "[blocked] That command is too dangerous."
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15
            )
            out = (result.stdout + result.stderr).strip()
            return out[:2000] if out else f"[exit {result.returncode}]"
        except subprocess.TimeoutExpired:
            return "[timeout] Command took >15s."
        except Exception as e:
            return f"[error] {e}"

    def _open(self, text: str) -> str:
        for trigger in ("open ", "launch ", "start "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                target = text[idx:].strip()
                break
        else:
            return "Usage: open <app or file>"
        sys = platform.system()
        try:
            if sys == "Darwin":
                subprocess.Popen(["open", target])
            elif sys == "Windows":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
            return f"Opening '{target}'..."
        except Exception as e:
            return f"[error] {e}"
