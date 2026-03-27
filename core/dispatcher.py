"""Dispatcher — loads all plugins, sorts by priority, routes input."""

import importlib
import pkgutil
import plugins as plugin_pkg
from plugins.base import PluginBase


class Dispatcher:
    def __init__(self):
        self._plugins: list[PluginBase] = []
        self._load_plugins()

    def _load_plugins(self):
        loaded = []
        for finder, name, _ in pkgutil.iter_modules(plugin_pkg.__path__):
            if name == "base":
                continue
            try:
                mod = importlib.import_module(f"plugins.{name}.plugin")
                cls = getattr(mod, "Plugin", None)
                if cls and issubclass(cls, PluginBase):
                    loaded.append(cls())
            except Exception as e:
                print(f"[dispatcher] failed to load plugin '{name}': {e}")
        # Sort by priority (lower = higher priority); default 100
        self._plugins = sorted(loaded, key=lambda p: getattr(p, "priority", 100))
        names = [type(p).__module__.split(".")[1] for p in self._plugins]
        print(f"[dispatcher] plugins (priority order): {names}")

    def dispatch(self, text: str, memory) -> str:
        for plugin in self._plugins:
            if plugin.matches(text):
                return plugin.run(text, memory)
        return "No plugin matched. Add one in plugins/."
