# plugins/brightness/plugin.py
"""
Brightness plugin — get or set screen brightness.
Requires: `brightnessctl` (Linux) or uses /sys/class/backlight fallback.
Triggers: 'brightness set 80', 'brightness up', 'brightness down', 'what is brightness'
"""
import re
import subprocess
from plugins.base import PluginBase


class Plugin(PluginBase):
    priority = 50

    _triggers = ("brightness", "screen brightness", "dim", "brighten")

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in self._triggers)

    def run(self, text: str, memory) -> str:
        try:
            t = text.lower()

            # Set brightness to a percentage
            m = re.search(r"set\s+(\d+)|brightness\s+(\d+)|(\d+)\s*%", t)
            if m:
                val = next(g for g in m.groups() if g is not None)
                return self._set(int(val))

            if "up" in t or "increase" in t or "higher" in t:
                return self._adjust("+10%")
            if "down" in t or "decrease" in t or "lower" in t:
                return self._adjust("-10%")
            if "max" in t or "full" in t:
                return self._set(100)
            if "min" in t or "off" in t:
                return self._set(0)

            return self._get()
        except Exception as e:
            return f"[brightness] error: {e}"

    # ------------------------------------------------------------------ #

    def _get(self) -> str:
        try:
            result = subprocess.run(
                ["brightnessctl", "get"],
                capture_output=True, text=True, timeout=5
            )
            max_r = subprocess.run(
                ["brightnessctl", "max"],
                capture_output=True, text=True, timeout=5
            )
            cur = int(result.stdout.strip())
            mx = int(max_r.stdout.strip())
            pct = round(cur / mx * 100)
            return f"Screen brightness is {pct}%."
        except FileNotFoundError:
            return self._get_sysfs()

    def _get_sysfs(self) -> str:
        import glob
        paths = glob.glob("/sys/class/backlight/*/brightness")
        if not paths:
            return "[brightness] Could not read brightness (no backlight device found)."
        cur = int(open(paths[0]).read().strip())
        mx_path = paths[0].replace("brightness", "max_brightness")
        mx = int(open(mx_path).read().strip())
        return f"Screen brightness is {round(cur / mx * 100)}%."

    def _set(self, pct: int) -> str:
        pct = max(0, min(100, pct))
        try:
            subprocess.run(
                ["brightnessctl", "set", f"{pct}%"],
                capture_output=True, timeout=5
            )
            return f"Brightness set to {pct}%."
        except FileNotFoundError:
            return self._set_sysfs(pct)

    def _set_sysfs(self, pct: int) -> str:
        import glob
        paths = glob.glob("/sys/class/backlight/*/brightness")
        if not paths:
            return "[brightness] Cannot set brightness (no backlight device found)."
        mx_path = paths[0].replace("brightness", "max_brightness")
        mx = int(open(mx_path).read().strip())
        new_val = round(pct / 100 * mx)
        try:
            open(paths[0], "w").write(str(new_val))
            return f"Brightness set to {pct}%."
        except PermissionError:
            return "[brightness] Permission denied. Try running with sudo or add udev rules."

    def _adjust(self, delta: str) -> str:
        try:
            subprocess.run(
                ["brightnessctl", "set", delta],
                capture_output=True, timeout=5
            )
            direction = "increased" if "+" in delta else "decreased"
            return f"Brightness {direction} by 10%."
        except FileNotFoundError:
            return "[brightness] brightnessctl not found. Install it or use 'brightness set <value>'."
