"""Plugin Registry — auto-discovers plugin capabilities at startup.

This is the bridge between self-describing plugins and the intent router.
At startup the dispatcher calls build() which:
  1. Iterates all loaded Plugin instances.
  2. Reads their capabilities list.
  3. Merges them into a unified INTENT_SCHEMA, TRIGGER_MAP, and EXAMPLES
     that the intent_router uses to build its LLM system prompt.

Adding a new plugin with capabilities never requires touching intent_router.py
or dispatcher.py.
"""

from __future__ import annotations
from plugins.base import PluginBase, PluginCapability


class PluginRegistry:
    def __init__(self):
        self.intent_schema : dict[str, dict] = {}
        self.trigger_map   : dict[str, str]  = {}
        self.examples      : list[tuple]     = []
        # plugin_name -> list[intent_str]
        self._intent_owners: dict[str, list[str]] = {}

    def build(self, plugins: dict[str, PluginBase]) -> None:
        """Scan all loaded plugins and collect their capabilities."""
        self.intent_schema.clear()
        self.trigger_map.clear()
        self.examples.clear()
        self._intent_owners.clear()

        for name, plugin in plugins.items():
            caps: list[PluginCapability] = getattr(plugin, "capabilities", []) or []
            owner_intents = []
            for cap in caps:
                self.intent_schema[cap.intent] = cap.args
                if cap.trigger_template:
                    self.trigger_map[cap.intent] = cap.trigger_template
                for phrase, args_dict in cap.examples:
                    self.examples.append((cap.intent, phrase, args_dict, cap.trigger_template))
                owner_intents.append(cap.intent)
            if owner_intents:
                self._intent_owners[name] = owner_intents

    def owner_of(self, intent: str) -> str | None:
        """Return the plugin name that owns a given intent, or None."""
        for name, intents in self._intent_owners.items():
            if intent in intents:
                return name
        return None

    def summary(self) -> str:
        lines = []
        for name, intents in self._intent_owners.items():
            lines.append(f"  {name}: {intents}")
        return "\n".join(lines) if lines else "  (no self-describing plugins loaded)"
