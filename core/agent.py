"""Agent — REPL loop."""

from core.config import get
from core.memory import Memory
from core.dispatcher import Dispatcher


class Agent:
    def __init__(self):
        self.name       = get("name", "Jarvis")
        self.debug      = get("debug", False)
        self.memory     = Memory()
        self.dispatcher = Dispatcher()

    def run(self):
        mode = __import__("core.config", fromlist=["get_llm_config"]).get_llm_config().get("_mode", "?")
        print(f"{self.name} online  [llm: {mode}]  Type 'exit' to quit.\n")
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{self.name} shutting down.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print(f"{self.name}: Goodbye.")
                break
            if user_input.lower() in ("help", "?"):
                print(_HELP)
                continue

            self.memory.add("user", user_input)
            response = self.dispatcher.dispatch(user_input, self.memory)
            self.memory.add("assistant", response)
            print(f"\n{self.name}: {response}\n")


_HELP = """
Built-in commands:
  exit / quit / bye    — shutdown Jarvis
  help / ?             — show this help

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
"""
