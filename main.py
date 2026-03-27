#!/usr/bin/env python3
"""J.A.R.V.I.S — CLI entrypoint."""

import argparse
import sys
import os

VERSION = "0.1.0"

BANNER = r"""
      _  ___    ____  _    __ _____
     | |/ _ \  |  _ \| |  / /|_   _|
  _  | | |_| | | |_) | | / /   | |
 | |_| |  _  | |  _ <| |/ /    | |
  \___/|_| |_| |_| \_\___/     |_|

  Just A Rather Very Intelligent System
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="J.A.R.V.I.S — Modular AI OS Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python main.py                         interactive REPL
  python main.py -c "show my cpu usage"  one-shot command
  python main.py -c "remind me in 10 minutes to take a break"
  python main.py --mode ollama           override LLM backend
  python main.py --debug                 show intent classification
  python main.py --no-llm-routing        use keyword matching fallback
  python main.py --list-plugins          list all loaded plugins
  python main.py --version               show version
        """,
    )

    parser.add_argument(
        "-c", "--command",
        metavar="CMD",
        help="run a single command and exit (non-interactive)",
    )
    parser.add_argument(
        "--mode",
        metavar="BACKEND",
        choices=["openai", "groq", "lmstudio", "ollama", "openrouter"],
        help="override llm_mode from config (openai/groq/lmstudio/ollama/openrouter)",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        help="override model name for the selected backend",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print intent classification for every input",
    )
    parser.add_argument(
        "--no-llm-routing",
        action="store_true",
        dest="no_llm_routing",
        help="disable LLM intent router, use keyword matching",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        dest="no_banner",
        help="suppress startup banner",
    )
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        dest="list_plugins",
        help="list all discovered plugins and exit",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default="config.yaml",
        help="path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"jarvis {VERSION}",
    )
    return parser


def apply_cli_overrides(args: argparse.Namespace):
    """Inject CLI flags into env so config.py and plugins pick them up."""
    if args.mode:
        os.environ["JARVIS_LLM_MODE"] = args.mode
    if args.model:
        os.environ["JARVIS_LLM_MODEL"] = args.model
    if args.debug:
        os.environ["JARVIS_DEBUG"] = "1"
    if args.no_llm_routing:
        os.environ["JARVIS_NO_LLM_ROUTING"] = "1"


def main():
    parser = build_parser()
    args   = parser.parse_args()

    # Apply overrides before any imports that read config
    apply_cli_overrides(args)

    # Lazy imports after env is set
    from core.config import load
    from core.agent  import Agent

    # Load config from custom path if given
    if args.config != "config.yaml":
        load(args.config)

    # --list-plugins
    if args.list_plugins:
        from core.dispatcher import Dispatcher
        d = Dispatcher()
        print("\nLoaded plugins (priority order):")
        for name, plugin in d._plugins.items():
            print(f"  {getattr(plugin, 'priority', 100):>4}  {name}")
        sys.exit(0)

    # Banner
    if not args.no_banner and not args.command:
        print(BANNER)

    # One-shot mode: -c "..."
    if args.command:
        agent = Agent()
        response = agent.dispatcher.dispatch(args.command, agent.memory)
        print(response)
        sys.exit(0)

    # Interactive REPL
    agent = Agent()
    agent.run()


if __name__ == "__main__":
    main()
