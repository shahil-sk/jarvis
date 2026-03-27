"""PluginBase — every plugin must subclass this."""

from abc import ABC, abstractmethod

class PluginBase(ABC):
    """
    Subclass this and implement:
      matches(text) -> bool   : return True if this plugin handles the input
      run(text, memory) -> str : execute and return a response string
    """

    @abstractmethod
    def matches(self, text: str) -> bool:
        ...

    @abstractmethod
    def run(self, text: str, memory) -> str:
        ...
