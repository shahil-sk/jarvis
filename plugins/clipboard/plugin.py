"""Clipboard plugin — read and write system clipboard."""

import subprocess
import platform
from plugins.base import PluginBase

_INTENTS = {
    ("clipboard", "what's in clipboard", "paste content") : "_read",
    ("copy to clipboard", "set clipboard")                 : "_write",
}


class Plugin(PluginBase):
    priority = 20

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text)
        return "Clipboard: could not parse intent."

    def _read(self, text: str) -> str:
        content = self._get_clipboard()
        if content is None:
            return "[error] Could not read clipboard."
        return f"Clipboard: {content[:500]}" if content else "Clipboard is empty."

    def _write(self, text: str) -> str:
        for trigger in ("copy to clipboard ", "set clipboard "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                content = text[idx:].strip()
                return self._set_clipboard(content)
        return "Usage: copy to clipboard <text>"

    def _get_clipboard(self):
        sys = platform.system()
        try:
            if sys == "Darwin":
                return subprocess.check_output(["pbpaste"], text=True)
            elif sys == "Windows":
                import ctypes
                ctypes.windll.user32.OpenClipboard(0)
                handle = ctypes.windll.user32.GetClipboardData(13)
                content = ctypes.c_char_p(handle).value
                ctypes.windll.user32.CloseClipboard()
                return content.decode(errors="replace") if content else ""
            else:  # Linux
                for tool in (["xclip", "-selection", "clipboard", "-o"],
                             ["xsel", "--clipboard", "--output"],
                             ["wl-paste"]):
                    try:
                        return subprocess.check_output(tool, text=True)
                    except FileNotFoundError:
                        continue
                return None
        except Exception:
            return None

    def _set_clipboard(self, content: str) -> str:
        sys = platform.system()
        try:
            if sys == "Darwin":
                subprocess.run(["pbcopy"], input=content, text=True)
            elif sys == "Windows":
                subprocess.run(["clip"], input=content, text=True)
            else:
                for tool in (["xclip", "-selection", "clipboard"],
                             ["xsel", "--clipboard", "--input"],
                             ["wl-copy"]):
                    try:
                        subprocess.run(tool, input=content, text=True)
                        break
                    except FileNotFoundError:
                        continue
            return f"Copied to clipboard: {content[:80]}{'...' if len(content) > 80 else ''}"
        except Exception as e:
            return f"[error] {e}"
