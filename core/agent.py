"""Agent — main REPL loop."""

from core.config import get
from core.memory import Memory
from core.dispatcher import Dispatcher

class Agent:
    def __init__(self):
        self.name = get("name", "Jarvis")
        self.debug = get("debug", False)
        self.memory = Memory()
        self.dispatcher = Dispatcher()

    def run(self):
        print(f"{self.name} online. Type 'exit' to quit.\n")
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

            self.memory.add("user", user_input)
            response = self.dispatcher.dispatch(user_input, self.memory)
            self.memory.add("assistant", response)
            print(f"{self.name}: {response}\n")
