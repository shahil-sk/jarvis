"""PluginBase — every plugin must subclass this.

Self-describing plugin contract
--------------------------------
Each plugin optionally declares a list of PluginCapability objects.
The dispatcher and intent_router read these at startup to auto-build
the intent schema, trigger map, and few-shot examples — no manual
wiring in dispatcher.py or intent_router.py required.

Minimal plugin (keyword-fallback only, no LLM routing):

    class Plugin(PluginBase):
        def matches(self, text): return "hello" in text.lower()
        def run(self, text, memory): return "Hello!"

Full plugin (LLM-routed, self-describing):

    class Plugin(PluginBase):
        capabilities = [
            PluginCapability(
                intent="weather.get",
                description="Get current weather for a city",
                args={"city": "str"},
                examples=[
                    ("what is the weather in London", {"city": "London"}),
                ],
                trigger_template="weather {city}",
            )
        ]

        def matches(self, text): return "weather" in text.lower()

        def run(self, text, memory): ...

        def run_intent(self, intent, args): ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PluginCapability:
    """
    Declares one intent that a plugin can handle.

    intent           : dot-namespaced id, e.g. "nmap.scan_normal"
    description      : one-line description shown to the LLM
    args             : {arg_name: "str" | "int" | "str?" | "int?"}
                       trailing '?' means optional
    examples         : list of (user_phrase, args_dict) for LLM few-shots
    trigger_template : canonical phrase with {arg} placeholders,
                       e.g. "nmap scan {target}"
    """
    intent           : str
    description      : str
    args             : dict = field(default_factory=dict)
    examples         : list = field(default_factory=list)
    trigger_template : str  = ""


class PluginBase(ABC):
    """
    Base class for all Jarvis plugins.

    priority (int)  : lower = higher priority. Default 100.
                      LLM fallback plugin uses 999 to always run last.
    capabilities    : list[PluginCapability] — declare what intents this
                      plugin handles. Auto-discovered at startup.
    """
    priority    : int  = 100
    capabilities: list = []   # override in subclass with PluginCapability list

    @abstractmethod
    def matches(self, text: str) -> bool:
        """Return True if this plugin can handle the given (trigger) text."""
        ...

    @abstractmethod
    def run(self, text: str, memory) -> str:
        """Execute the action and return a human-readable result string."""
        ...

    def run_intent(self, intent: str, args: dict) -> str:
        """
        Optional typed entry point called by the dispatcher when using
        LLM routing.  Default falls back to run() with a trigger string.
        Override this in plugins that benefit from typed args.
        """
        trigger = self._build_trigger_from_args(intent, args)
        return self.run(trigger, None)

    def _build_trigger_from_args(self, intent: str, args: dict) -> str:
        for cap in self.capabilities:
            if cap.intent == intent and cap.trigger_template:
                try:
                    return cap.trigger_template.format_map(args)
                except KeyError:
                    return cap.trigger_template
        return intent
