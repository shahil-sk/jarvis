"""Agent — REPL loop with graceful error recovery and intent logging."""

import traceback
from core.config import get
from core.memory import Memory
from core.dispatcher import Dispatcher


class Agent:
    def __init__(self):
        self.name       = get("name", "Jarvis")
        self.debug      = get("debug", False)
        self.memory     = Memory()
        self.dispatcher = Dispatcher()

    def run(self) -> None:
        """Interactive REPL — catches all errors per-turn so one crash never kills the session."""
        try:
            mode = __import__("core.config", fromlist=["get_llm_config"]).get_llm_config().get("_mode", "?")
        except Exception:
            mode = "unknown"

        print(f"{self.name} online  [llm: {mode}]  Type 'exit' to quit.\n")

        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 5

        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                print(f"\n{self.name}: EOF received — shutting down.")
                break
            except KeyboardInterrupt:
                print(f"\n{self.name}: Interrupted. Type 'exit' to quit.")
                continue

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print(f"{self.name}: Goodbye.")
                break
            if user_input.lower() in ("help", "?"):
                print(_HELP)
                continue
            if user_input.lower() == "reload plugins":
                print(self.dispatcher.reload_plugins())
                continue
            if user_input.lower() in ("memory stats", "db stats"):
                print(str(self.memory.stats()))
                continue
            if user_input.lower() == "intent log":
                intents = self.memory.recent_intents(10)
                if not intents:
                    print("No intents logged yet.")
                else:
                    for row in intents:
                        print(f"  {row.get('intent'):30s}  trigger={row.get('trigger')!r}")
                continue

            try:
                self.memory.add("user", user_input)

                # Classify intent first so we can log it
                from core import intent_router
                try:
                    classified = intent_router.classify(user_input)
                except Exception:
                    classified = {"intent": "llm.chat", "args": {}, "trigger": user_input}

                # Log intent to SQLite
                self.memory.log_intent(
                    user_input,
                    intent  = classified.get("intent", "llm.chat"),
                    trigger = classified.get("trigger", ""),
                    args    = classified.get("args", {}),
                )

                # Dispatch (will re-classify internally, but that's cached via the LLM call)
                response = self.dispatcher.dispatch(user_input, self.memory)

                if not isinstance(response, str):
                    response = str(response) if response is not None else ""

                self.memory.add("assistant", response)
                print(f"\n{self.name}: {response}\n")
                consecutive_errors = 0

            except KeyboardInterrupt:
                print(f"\n{self.name}: Command interrupted.")
                consecutive_errors = 0
                continue

            except Exception as exc:
                consecutive_errors += 1
                print(f"\n{self.name}: Something went wrong — {exc}")
                if self.debug:
                    traceback.print_exc()
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"{self.name}: Too many consecutive errors ({MAX_CONSECUTIVE_ERRORS}). "
                          "Please check your config or run with --debug.")
                    consecutive_errors = 0


_HELP = """
Built-in commands:
  exit / quit / bye    — shutdown Jarvis
  help / ?             — show this help
  reload plugins       — hot-reload all plugins without restarting
  memory stats         — show DB row counts and path
  intent log           — show the last 10 classified intents

Just talk naturally. Examples:
  how much ram am i using
  remind me in 30 minutes to check the build
  list open issues in jarvis
  find all .log files
  is github.com up
  open my dev workspace
  save note buy milk #personal
  show my notes
  run git pull
  kill firefox
  what's my public ip
  brightness set 70
  clipboard history
  env PATH
  start stopwatch build
"""
