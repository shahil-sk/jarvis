"""Hello plugin — example plugin, greets the user."""

from plugins.base import PluginBase

class Plugin(PluginBase):
    _triggers = ("hello", "hi", "hey", "howdy")

    def matches(self, text: str) -> bool:
        return any(t in text.lower() for t in self._triggers)

    def run(self, text: str, memory) -> str:
        history = memory.last(3)
        if len(history) > 2:
            return "Hey again! What can I do for you?"
        return "Hello! I'm Jarvis. What do you need?"
