# plugins/stopwatch/plugin.py
"""
Stopwatch plugin — named stopwatches you can start, stop, pause, resume, and lap.

All state is in-process (module-level dict). Multiple named stopwatches are
supported so you can time several things at once.

Triggers:
  'start stopwatch'             → starts/resumes the default stopwatch
  'start stopwatch build'       → named stopwatch 'build'
  'stop stopwatch'              → stop and show elapsed
  'pause stopwatch'             → pause
  'resume stopwatch'            → resume
  'lap stopwatch'               → record a lap without stopping
  'elapsed stopwatch' / 'time'  → show current elapsed
  'list stopwatches'            → show all active watches
  'reset stopwatch'             → reset to zero
"""
import re
import time
from plugins.base import PluginBase

# Module-level store: name → {start, elapsed, laps, running, paused_at}
_watches: dict = {}


class Plugin(PluginBase):
    priority = 55  # before timer plugin if one exists

    _triggers = (
        "stopwatch",
        "start timing",
        "stop timing",
        "lap time",
    )

    def matches(self, text: str) -> bool:
        return any(kw in text.lower() for kw in self._triggers)

    def run(self, text: str, memory) -> str:
        try:
            t = text.lower()
            name = self._extract_name(t)

            if "list" in t:
                return self._list_all()
            if "start" in t or "begin" in t:
                return self._start(name)
            if "stop" in t or "finish" in t or "end" in t:
                return self._stop(name)
            if "pause" in t:
                return self._pause(name)
            if "resume" in t or "continue" in t:
                return self._resume(name)
            if "lap" in t:
                return self._lap(name)
            if "reset" in t or "clear" in t:
                return self._reset(name)
            # Default: show elapsed
            return self._elapsed(name)
        except Exception as e:
            return f"[stopwatch] error: {e}"

    # ------------------------------------------------------------------ #

    def _extract_name(self, t: str) -> str:
        """Extract optional stopwatch name from text, default to 'default'."""
        m = re.search(
            r"stopwatch\s+(\w+)|timing\s+(\w+)", t
        )
        if m:
            candidate = m.group(1) or m.group(2)
            if candidate not in (
                "start", "stop", "pause", "resume", "lap", "reset",
                "list", "clear", "elapsed", "time", "finish", "end",
                "begin", "continue",
            ):
                return candidate
        return "default"

    def _start(self, name: str) -> str:
        if name in _watches and _watches[name]["running"]:
            return f"Stopwatch '{name}' is already running."
        if name in _watches and _watches[name].get("paused_at"):
            return self._resume(name)
        _watches[name] = {
            "start": time.monotonic(),
            "elapsed": 0.0,
            "laps": [],
            "running": True,
            "paused_at": None,
        }
        return f"Stopwatch '{name}' started."

    def _stop(self, name: str) -> str:
        w = _watches.get(name)
        if not w:
            return f"Stopwatch '{name}' is not running."
        total = w["elapsed"] + (time.monotonic() - w["start"] if w["running"] else 0)
        del _watches[name]
        return f"Stopwatch '{name}' stopped. Total time: {self._fmt(total)}."

    def _pause(self, name: str) -> str:
        w = _watches.get(name)
        if not w or not w["running"]:
            return f"Stopwatch '{name}' is not running."
        w["elapsed"] += time.monotonic() - w["start"]
        w["running"] = False
        w["paused_at"] = time.monotonic()
        return f"Stopwatch '{name}' paused at {self._fmt(w['elapsed'])}."

    def _resume(self, name: str) -> str:
        w = _watches.get(name)
        if not w:
            return f"Stopwatch '{name}' not found. Use 'start stopwatch {name}' first."
        if w["running"]:
            return f"Stopwatch '{name}' is already running."
        w["start"] = time.monotonic()
        w["running"] = True
        w["paused_at"] = None
        return f"Stopwatch '{name}' resumed."

    def _lap(self, name: str) -> str:
        w = _watches.get(name)
        if not w or not w["running"]:
            return f"Stopwatch '{name}' is not running."
        elapsed = w["elapsed"] + (time.monotonic() - w["start"])
        lap_num = len(w["laps"]) + 1
        prev = w["laps"][-1] if w["laps"] else 0.0
        w["laps"].append(elapsed)
        return (
            f"Lap {lap_num} — split: {self._fmt(elapsed - prev)}, "
            f"total: {self._fmt(elapsed)}."
        )

    def _reset(self, name: str) -> str:
        _watches.pop(name, None)
        return f"Stopwatch '{name}' reset."

    def _elapsed(self, name: str) -> str:
        w = _watches.get(name)
        if not w:
            return f"No stopwatch named '{name}' is active. Say 'start stopwatch' to begin."
        total = w["elapsed"] + (time.monotonic() - w["start"] if w["running"] else 0)
        status = "running" if w["running"] else "paused"
        laps = f", {len(w['laps'])} lap(s) recorded" if w["laps"] else ""
        return f"Stopwatch '{name}' ({status}): {self._fmt(total)}{laps}."

    def _list_all(self) -> str:
        if not _watches:
            return "No active stopwatches."
        lines = []
        for name, w in _watches.items():
            total = w["elapsed"] + (time.monotonic() - w["start"] if w["running"] else 0)
            status = "▶ running" if w["running"] else "⏸ paused"
            lines.append(f"  {name}: {self._fmt(total)} ({status}, {len(w['laps'])} laps)")
        return "Active stopwatches:\n" + "\n".join(lines)

    @staticmethod
    def _fmt(seconds: float) -> str:
        """Format seconds as H:MM:SS.mm"""
        ms = int((seconds % 1) * 100)
        s = int(seconds) % 60
        m = int(seconds) // 60 % 60
        h = int(seconds) // 3600
        if h:
            return f"{h}:{m:02d}:{s:02d}.{ms:02d}"
        return f"{m:02d}:{s:02d}.{ms:02d}"
