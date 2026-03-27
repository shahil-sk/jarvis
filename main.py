#!/usr/bin/env python3
"""J.A.R.V.I.S - Entrypoint"""

from core.agent import Agent

if __name__ == "__main__":
    agent = Agent()
    agent.run()
