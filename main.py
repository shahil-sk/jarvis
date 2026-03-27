#!/usr/bin/env python3
"""J.A.R.V.I.S — CLI entrypoint."""

import argparse
import sys
import os
import traceback

VERSION = "0.2.0"

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
    parser.add_argument("-c", "--command", metavar="CMD",
        help="run a single command and exit (non-interactive)")
    parser.add_argument("--mode", metavar="BACKEND",
        choices=["openai", "groq", "lmstudio", "ollama", "openrouter"],
        help="override llm_mode from config")
    parser.add_argument("--model", metavar="NAME",
        help="override model name for the selected backend")
    parser.add_argument("--debug", action="store_true",
        help="print intent classification for every input")
    parser.add_argument("--no-llm-routing", action="store_true", dest="no_llm_routing",
        help="disable LLM intent router, use keyword matching")
    parser.add_argument("--no-banner", action="store_true", dest="no_banner",
        help="suppress startup banner")
    parser.add_argument("--list-plugins", action="store_true", dest="list_plugins",
        help="list all discovered plugins and exit")
    parser.add_argument("--config", metavar="PATH", default="config.yaml",
        help="path to config file (default: config.yaml)")
    parser.add_argument("--version", "-v", action="version", version=f"jarvis {VERSION}")
    return parser


def apply_cli_overrides(args: argparse.Namespace) -> None:
    if args.mode:
        os.environ["JARVIS_LLM_MODE"] = args.mode
    if args.model:
        os.environ["JARVIS_LLM_MODEL"] = args.model
    if args.debug:
        os.environ["JARVIS_DEBUG"] = "1"
    if args.no_llm_routing:
        os.environ["JARVIS_NO_LLM_ROUTING"] = "1"


def _safe_import_core():
    """Import core modules with a friendly error if the environment is broken."""
    try:
        from core.config import load  # noqa: F401
        from core.agent import Agent  # noqa: F401
        return load, Agent
    except ImportError as exc:
        print(f"[jarvis] Failed to import core modules: {exc}")
        print("  Make sure you're running from the repo root and have installed requirements:")
        print("    pip install -r requirements.txt")
        sys.exit(1)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    apply_cli_overrides(args)

    load, Agent = _safe_import_core()

    if args.config != "config.yaml":
        try:
            load(args.config)
        except FileNotFoundError:
            print(f"[jarvis] Config file not found: {args.config}")
            sys.exit(1)
        except Exception as exc:
            print(f"[jarvis] Failed to load config '{args.config}': {exc}")
            sys.exit(1)

    # --list-plugins: enumerate and exit
    if args.list_plugins:
        try:
            from core.dispatcher import Dispatcher
            d = Dispatcher()
            print("\nLoaded plugins (priority order):")
            for name, plugin in d._plugins.items():
                print(f"  {getattr(plugin, 'priority', 100):>4}  {name}")
            if d._failed_plugins:
                print("\nFailed to load:")
                for name, reason in d._failed_plugins.items():
                    print(f"  ✗  {name}: {reason}")
        except Exception as exc:
            print(f"[jarvis] Could not list plugins: {exc}")
        sys.exit(0)

    # Banner (interactive mode only)
    if not args.no_banner and not args.command:
        print(BANNER)

    # One-shot mode
    if args.command:
        try:
            agent = Agent()
            response = agent.dispatcher.dispatch(args.command, agent.memory)
            print(response)
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            print(f"[jarvis] Unexpected error: {exc}")
            if os.environ.get("JARVIS_DEBUG"):
                traceback.print_exc()
        sys.exit(0)

    # Interactive REPL
    try:
        agent = Agent()
        agent.run()
    except Exception as exc:
        print(f"[jarvis] Fatal startup error: {exc}")
        if os.environ.get("JARVIS_DEBUG"):
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
