"""Short-term session memory — simple ring buffer, no persistence."""

from collections import deque
from core.config import get

class Memory:
    def __init__(self):
        self._max = get("memory", {}).get("max_entries", 50)
        self._store: deque = deque(maxlen=self._max)

    def add(self, role: str, content: str):
        self._store.append({"role": role, "content": content})

    def history(self) -> list:
        return list(self._store)

    def clear(self):
        self._store.clear()

    def last(self, n: int = 5) -> list:
        return list(self._store)[-n:]
