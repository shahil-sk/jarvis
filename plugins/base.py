"""PluginBase — every plugin must subclass this."""

from abc import ABC, abstractmethod


class PluginBase(ABC):
    """
    priority (int): lower = runs first. Default 100.
                    LLM fallback uses 999 to always run last.
    """
    priority: int = 100

    @abstractmethod
    def matches(self, text: str) -> bool: ...

    @abstractmethod
    def run(self, text: str, memory) -> str: ...
