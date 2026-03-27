"""System plugin — shell, stats, uptime, open, sysinfo, env, services."""

import os
import time
import platform
import subprocess
from plugins.base import PluginBase, PluginCapability

_START_TIME = time.time()

_BLOCKED_CMDS = ("rm -rf /", "mkfs", "> /dev/sd", "dd if=")


class Plugin(PluginBase):
    priority = 10

    capabilities = [
        PluginCapability(
            intent="system.stats",
            description="Show CPU, RAM, and disk usage",
            args={},
            trigger_template="system stats",
            examples=[("how much ram am i using", {}), ("cpu usage", {}), ("system stats", {})],
        ),
        PluginCapability(
            intent="system.uptime",
            description="Show how long Jarvis has been running",
            args={},
            trigger_template="system uptime",
            examples=[("how long has jarvis been running", {}), ("uptime", {})],
        ),
        PluginCapability(
            intent="system.sysinfo",
            description="Show OS, machine, python, and CWD info",
            args={},
            trigger_template="system info",
            examples=[("what os am i on", {}), ("system info", {}), ("platform info", {})],
        ),
        PluginCapability(
            intent="system.shell",
            description="Run any shell command on the system",
            args={"cmd": "str"},
            trigger_template="run {cmd}",
            examples=[
                ("run git status", {"cmd": "git status"}),
                ("execute ls -la", {"cmd": "ls -la"}),
                ("run df -h", {"cmd": "df -h"}),
            ],
        ),
        PluginCapability(
            intent="system.open",
            description="Open an application, file, or URL",
            args={"target": "str"},
            trigger_template="open {target}",
            examples=[
                ("open firefox", {"target": "firefox"}),
                ("launch terminal", {"target": "terminal"}),
                ("open /home/user/file.pdf", {"target": "/home/user/file.pdf"}),
            ],
        ),
        PluginCapability(
            intent="system.env",
            description="Get an environment variable value",
            args={"key": "str?"},
            trigger_template="env {key}",
            examples=[
                ("what is PATH", {"key": "PATH"}),
                ("show env HOME", {"key": "HOME"}),
                ("list all env vars", {}),
            ],
        ),
        PluginCapability(
            intent="system.setenv",
            description="Set an environment variable",
            args={"key": "str", "value": "str"},
            trigger_template="set env {key}={value}",
            examples=[
                ("set env DEBUG=true", {"key": "DEBUG", "value": "true"}),
            ],
        ),
        PluginCapability(
            intent="system.services",
            description="List running systemd/launchd services",
            args={},
            trigger_template="list services",
            examples=[("show running services", {}), ("list services", {})],
        ),
        PluginCapability(
            intent="system.battery",
            description="Show battery level and charging status",
            args={},
            trigger_template="battery status",
            examples=[("what is my battery level", {}), ("battery status", {})],
        ),
        PluginCapability(
            intent="system.reboot",
            description="Reboot the system",
            args={"delay": "int?"},
            trigger_template="reboot system",
            examples=[("reboot now", {}), ("restart the machine", {})],
        ),
        PluginCapability(
            intent="system.shutdown",
            description="Shut down the system",
            args={"delay": "int?"},
            trigger_template="shutdown system",
            examples=[("shutdown", {}), ("power off", {})],
        ),
    ]

    def matches(self, text: str) -> bool:
        keywords = (
            "cpu", "ram", "memory", "disk", "stats", "usage",
            "uptime", "run ", "exec ", "shell ", "open ", "launch ",
            "start ", "os ", "system info", "platform", "env ",
            "environment", "getenv", "set env", "export ",
            "services", "battery", "reboot", "shutdown", "restart",
        )
        t = text.lower()
        return any(kw in t for kw in keywords)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if any(k in t for k in ("cpu", "ram", "memory", "disk", "stats", "usage")):
            return self._stats(text)
        if "uptime" in t:
            return self._uptime(text)
        if any(k in t for k in ("os ", "system info", "platform", "sysinfo")):
            return self._sysinfo(text)
        if any(k in t for k in ("run ", "exec ", "shell ", "$ ")):
            return self._shell(text)
        if any(k in t for k in ("open ", "launch ", "start ")):
            return self._open(text)
        if "set env" in t or "export " in t:
            return self._setenv(text)
        if any(k in t for k in ("env ", "environment variable", "getenv")):
            return self._env(text)
        if "service" in t:
            return self._services()
        if "battery" in t:
            return self._battery()
        if "reboot" in t or ("restart" in t and "service" not in t):
            return self._reboot(text)
        if "shutdown" in t or "power off" in t:
            return self._shutdown(text)
        return "System: could not parse intent."

    def run_intent(self, intent: str, args: dict) -> str:
        dispatch = {
            "system.stats"   : lambda: self._stats(""),
            "system.uptime"  : lambda: self._uptime(""),
            "system.sysinfo" : lambda: self._sysinfo(""),
            "system.shell"   : lambda: self._shell(f"run {args.get('cmd', '')}"),
            "system.open"    : lambda: self._open(f"open {args.get('target', '')}"),
            "system.env"     : lambda: self._env(f"env {args.get('key', '')}"),
            "system.setenv"  : lambda: self._setenv(f"set env {args.get('key', '')}={args.get('value', '')}"),
            "system.services": lambda: self._services(),
            "system.battery" : lambda: self._battery(),
            "system.reboot"  : lambda: self._reboot(""),
            "system.shutdown": lambda: self._shutdown(""),
        }
        fn = dispatch.get(intent)
        return fn() if fn else f"Unknown system intent: {intent}"

    def _stats(self, _) -> str:
        try:
            import psutil
            cpu   = psutil.cpu_percent(interval=0.5)
            ram   = psutil.virtual_memory()
            disk  = psutil.disk_usage("/")
            swap  = psutil.swap_memory()
            cores = psutil.cpu_count(logical=True)
            lines = [
                f"CPU  : {cpu}%  ({cores} logical cores)",
                f"RAM  : {ram.used // 1024**2}MB / {ram.total // 1024**2}MB ({ram.percent}%)",
                f"Swap : {swap.used // 1024**2}MB / {swap.total // 1024**2}MB ({swap.percent}%)",
                f"Disk : {disk.used // 1024**3}GB / {disk.total // 1024**3}GB ({disk.percent}%)",
            ]
            # Top 5 CPU consumers
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent"]),
                key=lambda p: p.info.get("cpu_percent") or 0, reverse=True
            )[:5]
            lines.append("\nTop CPU processes:")
            for p in procs:
                lines.append(f"  {p.info['name']:<25} {p.info['cpu_percent'] or 0:.1f}%")
            return "\n".join(lines)
        except ImportError:
            return "Install psutil: pip install psutil"

    def _uptime(self, _) -> str:
        secs = int(time.time() - _START_TIME)
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        try:
            import psutil, datetime
            boot   = psutil.boot_time()
            booted = datetime.datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M")
            sys_up = int(time.time() - boot)
            sh, sr = divmod(sys_up, 3600)
            sm, ss = divmod(sr, 60)
            return (
                f"Jarvis uptime : {h}h {m}m {s}s\n"
                f"System uptime : {sh}h {sm}m {ss}s  (booted {booted})"
            )
        except ImportError:
            return f"Jarvis uptime: {h}h {m}m {s}s"

    def _sysinfo(self, _) -> str:
        try:
            import psutil
            cpu_freq = psutil.cpu_freq()
            freq_str = f"{cpu_freq.current:.0f}MHz" if cpu_freq else "N/A"
        except ImportError:
            freq_str = "N/A"
        return "\n".join([
            f"OS      : {platform.system()} {platform.release()} ({platform.version()})",
            f"Machine : {platform.machine()}",
            f"Python  : {platform.python_version()}",
            f"CPU     : {platform.processor() or 'N/A'}  @{freq_str}",
            f"Cores   : {os.cpu_count()}",
            f"CWD     : {os.getcwd()}",
            f"User    : {os.environ.get('USER') or os.environ.get('USERNAME', 'unknown')}",
        ])

    def _env(self, text: str) -> str:
        key = ""
        for trigger in ("env ", "getenv ", "environment variable ", "what is ", "show env "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                key = text[idx:].strip().split()[0] if text[idx:].strip() else ""
                break
        if not key:
            items = list(os.environ.items())[:40]
            return "\n".join(f"{k}={v}" for k, v in sorted(items))
        val = os.environ.get(key)
        return f"{key}={val}" if val is not None else f"{key} is not set"

    def _setenv(self, text: str) -> str:
        for trigger in ("set env ", "export ", "setenv "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                arg = text[idx:].strip()
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    os.environ[k.strip()] = v.strip()
                    return f"Set {k.strip()}={v.strip()}"
        return "Usage: set env KEY=VALUE"

    def _shell(self, text: str) -> str:
        cmd = ""
        for trigger in ("run ", "exec ", "shell ", "$ ", "execute "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                cmd = text[idx:].strip()
                break
        if not cmd:
            return "No command found.  Usage: run <command>"
        if any(b in cmd for b in _BLOCKED_CMDS):
            return "[blocked] That command is too dangerous to run."
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                env=os.environ.copy()
            )
            out = (result.stdout + result.stderr).strip()
            if not out:
                return f"[exit {result.returncode}] (no output)"
            return out[:4000]
        except subprocess.TimeoutExpired:
            return "[timeout] Command took >30s."
        except Exception as e:
            return f"[error] {e}"

    def _open(self, text: str) -> str:
        target = ""
        for trigger in ("open ", "launch ", "start "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                target = text[idx:].strip()
                break
        if not target:
            return "Usage: open <app or file>"
        sys_name = platform.system()
        try:
            if sys_name == "Darwin":
                subprocess.Popen(["open", target])
            elif sys_name == "Windows":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
            return f"Opening '{target}'..."
        except Exception as e:
            return f"[error] {e}"

    def _services(self) -> str:
        sys_name = platform.system()
        try:
            if sys_name == "Linux":
                r = subprocess.run(
                    ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--plain"],
                    capture_output=True, text=True, timeout=10
                )
                lines = r.stdout.strip().splitlines()
                return "\n".join(lines[:30])
            elif sys_name == "Darwin":
                r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
                return r.stdout.strip()[:3000]
            else:
                r = subprocess.run(["sc", "query", "type=", "service", "state=", "running"],
                                   capture_output=True, text=True, timeout=10)
                return r.stdout.strip()[:3000]
        except Exception as e:
            return f"[error] {e}"

    def _battery(self) -> str:
        try:
            import psutil
            bat = psutil.sensors_battery()
            if not bat:
                return "No battery found (desktop machine or driver unavailable)."
            status = "Charging" if bat.power_plugged else "Discharging"
            secs   = bat.secsleft
            if secs and secs > 0:
                h, m = divmod(secs // 60, 60)
                time_left = f"  ({h}h {m}m remaining)"
            else:
                time_left = ""
            return f"Battery: {bat.percent:.0f}%  {status}{time_left}"
        except ImportError:
            return "Install psutil: pip install psutil"

    def _reboot(self, _) -> str:
        sys_name = platform.system()
        try:
            if sys_name == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "5"])
            else:
                subprocess.run(["sudo", "reboot"])
            return "Rebooting..."
        except Exception as e:
            return f"[error] {e}"

    def _shutdown(self, _) -> str:
        sys_name = platform.system()
        try:
            if sys_name == "Windows":
                subprocess.run(["shutdown", "/s", "/t", "5"])
            elif sys_name == "Darwin":
                subprocess.run(["sudo", "shutdown", "-h", "now"])
            else:
                subprocess.run(["sudo", "shutdown", "-h", "now"])
            return "Shutting down..."
        except Exception as e:
            return f"[error] {e}"
