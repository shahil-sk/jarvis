"""Hello plugin — greetings, help, status, and plugin listing."""

from plugins.base import PluginBase, PluginCapability

_GREETINGS = (
    "hello", "hi", "hey", "good morning", "good afternoon",
    "good evening", "greetings", "howdy", "sup",
)

_HELP_KEYWORDS  = ("help", "what can you do", "commands", "features")
_STATUS_KEYWORDS = ("status", "are you alive", "are you there", "ping jarvis")


class Plugin(PluginBase):
    priority = 5  # responds first before any other plugin

    capabilities = [
        PluginCapability(
            intent="jarvis.greet",
            description="Greet the user and say hello",
            args={},
            trigger_template="hello",
            examples=[
                ("hello jarvis", {}),
                ("hey there", {}),
                ("good morning", {}),
            ],
        ),
        PluginCapability(
            intent="jarvis.help",
            description="Show available capabilities and example commands",
            args={},
            trigger_template="help",
            examples=[
                ("what can you do", {}),
                ("help", {}),
                ("show me commands", {}),
            ],
        ),
        PluginCapability(
            intent="jarvis.status",
            description="Check if Jarvis is online and responsive",
            args={},
            trigger_template="status",
            examples=[
                ("are you alive", {}),
                ("status", {}),
                ("ping jarvis", {}),
            ],
        ),
    ]

    def matches(self, text: str) -> bool:
        t = text.lower().strip()
        return (
            any(t.startswith(g) for g in _GREETINGS)
            or any(k in t for k in _HELP_KEYWORDS)
            or any(k in t for k in _STATUS_KEYWORDS)
        )

    def run(self, text: str, memory) -> str:
        t = text.lower().strip()
        if any(t.startswith(g) for g in _GREETINGS):
            return self._greet()
        if any(k in t for k in _HELP_KEYWORDS):
            return self._help()
        if any(k in t for k in _STATUS_KEYWORDS):
            return self._status()
        return self._greet()

    def run_intent(self, intent: str, args: dict) -> str:
        return {
            "jarvis.greet" : self._greet,
            "jarvis.help"  : self._help,
            "jarvis.status": self._status,
        }.get(intent, self._greet)()

    def _greet(self) -> str:
        import random, datetime
        hour = datetime.datetime.now().hour
        time_greeting = (
            "Good morning" if hour < 12
            else "Good afternoon" if hour < 17
            else "Good evening"
        )
        responses = [
            f"{time_greeting}. All systems operational. How can I assist?",
            f"{time_greeting}. Jarvis online. What do you need?",
            f"{time_greeting}. Ready and waiting.",
        ]
        return random.choice(responses)

    def _help(self) -> str:
        return """Jarvis Capabilities
-------------------
System     : system stats, uptime, sysinfo, battery, services, run <cmd>, open <app>
Filesystem : find, read, write, list, move, copy, delete, mkdir, stat, tree, disk usage
Process    : list processes, kill <name>, find process <name>, top 10, suspend, resume
Network    : ping, curl, download, my ip, ip info, dns, check url, speedtest, traceroute, headers, interfaces
Nmap       : scan, stealth scan, full scan, version scan, os detect, vuln scan, quick scan
Scheduler  : remind me in X minutes, remind at 5pm, list reminders, cancel reminder
Todo       : add todo, list todos, complete, delete, search, stats
Notes      : save note, list notes, search notes
GitHub     : list repos, list issues, create issue, list PRs, list commits
Web        : summarize url, read url, search web, news <topic>
LLM        : anything else goes to the AI brain

Type any natural sentence — Jarvis figures out what to do."""

    def _status(self) -> str:
        import time
        return (
            f"Jarvis online. All systems nominal.\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
