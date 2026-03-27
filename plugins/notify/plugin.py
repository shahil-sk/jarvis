"""Notify plugin — send desktop notifications cross-platform."""

import subprocess
import platform
from plugins.base import PluginBase

_INTENTS = {
    ("notify ", "notification ", "alert me", "remind me", "send notification"),
}


class Plugin(PluginBase):
    priority = 18

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        for trigger in ("notify ", "notification ", "alert me ", "remind me ", "send notification "):
            if trigger in text.lower():
                idx = text.lower().index(trigger) + len(trigger)
                message = text[idx:].strip()
                return self._notify("Jarvis", message)
        return "Usage: notify <message>"

    def _notify(self, title: str, message: str) -> str:
        sys = platform.system()
        try:
            if sys == "Darwin":
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script])
            elif sys == "Windows":
                # Uses PowerShell toast
                ps = (
                    f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;'
                    f'$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText01);'
                    f'$template.SelectSingleNode("//text[@id=1]").InnerText = "{message}";'
                    f'$toast = [Windows.UI.Notifications.ToastNotification]::new($template);'
                    f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{title}").Show($toast);'
                )
                subprocess.run(["powershell", "-Command", ps], capture_output=True)
            else:  # Linux
                subprocess.run(["notify-send", title, message])
            return f"Notification sent: {message}"
        except FileNotFoundError:
            return "[notify] notify-send not found. Install: sudo apt install libnotify-bin"
        except Exception as e:
            return f"[notify error] {e}"
