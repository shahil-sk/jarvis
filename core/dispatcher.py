"""Dispatcher — loads all plugins and routes user input to the right one."""

import importlib
import pkgutil
import plugins as plugin_pkg
from plugins.base import PluginBase

class Dispatcher:
    def __init__(self):
        self._plugins: list[PluginBase] = []
        self._load_plugins()

    def _load_plugins(self):
        for finder, name, _ in pkgutil.iter_modules(plugin_pkg.__path__):
            if name == "base":
                continue
            try:
                mod = importlib.import_module(f"plugins.{name}.plugin")
                cls = getattr(mod, "Plugin", None)
                if cls and issubclass(cls, PluginBase):
                    self._plugins.append(cls())
            except Exception as e:
                print(f"[dispatcher] failed to load plugin '{name}': {e}")
        print(f"[dispatcher] loaded {len(self._plugins)} plugin(s)")

    def dispatch(self, text: str, memory) -> str:
        for plugin in self._plugins:
            if plugin.matches(text):
                return plugin.run(text, memory)
        return "I don't know how to handle that yet. Try adding a plugin!"
