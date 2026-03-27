"""Dispatcher — LLM intent routing → plugin method calls.

Key robustness guarantees
─────────────────────────
• Every plugin is loaded inside an isolated try/except; one broken plugin
  never prevents the others from loading.
• _failed_plugins dict records {name: reason} for every load failure so
  `--list-plugins` can surface them.
• _route() wraps every plugin call in try/except and returns an error string
  instead of raising, so a buggy plugin can never crash the REPL.
• dispatch() itself is wrapped — it always returns a str, never None.
• validate_plugin() checks the PluginBase contract at load time and logs
  warnings for plugins that are structurally wrong without refusing to run them.
"""

import importlib
import pkgutil
import traceback
import plugins as plugin_pkg
from plugins.base import PluginBase
from core import intent_router
from core.config import get

_PRI_MAP = {"low": 1, "medium": 2, "med": 2, "high": 3, "urgent": 4, "critical": 4}


def _validate_plugin(name: str, instance: PluginBase) -> list[str]:
    """Return a list of warning strings for structural issues (non-fatal)."""
    warnings = []
    if not callable(getattr(instance, "matches", None)):
        warnings.append("missing callable 'matches(text)'")
    if not callable(getattr(instance, "run", None)):
        warnings.append("missing callable 'run(text, memory)'")
    if not isinstance(getattr(instance, "priority", None), int):
        warnings.append("'priority' is not an int — defaulting to 100")
        instance.priority = 100
    return warnings


class Dispatcher:
    def __init__(self):
        self._plugins: dict[str, PluginBase] = {}
        self._failed_plugins: dict[str, str] = {}   # name → error reason
        self._load_plugins()
        self._use_llm_routing = get("llm_routing", True)

    # ------------------------------------------------------------------ #
    # Plugin loading
    # ------------------------------------------------------------------ #

    def _load_plugins(self) -> None:
        loaded: list[tuple[str, PluginBase]] = []

        for _, name, _ in pkgutil.iter_modules(plugin_pkg.__path__):
            if name == "base":
                continue
            try:
                mod = importlib.import_module(f"plugins.{name}.plugin")
            except Exception as exc:
                reason = f"import error: {exc}"
                self._failed_plugins[name] = reason
                print(f"[dispatcher] ✗ '{name}' failed to import: {exc}")
                continue

            cls = getattr(mod, "Plugin", None)
            if cls is None:
                reason = "no class named 'Plugin' found in plugin.py"
                self._failed_plugins[name] = reason
                print(f"[dispatcher] ✗ '{name}': {reason}")
                continue

            if not (isinstance(cls, type) and issubclass(cls, PluginBase)):
                reason = "'Plugin' does not subclass PluginBase"
                self._failed_plugins[name] = reason
                print(f"[dispatcher] ✗ '{name}': {reason}")
                continue

            try:
                instance = cls()
            except Exception as exc:
                reason = f"__init__ raised: {exc}"
                self._failed_plugins[name] = reason
                print(f"[dispatcher] ✗ '{name}' failed to instantiate: {exc}")
                continue

            # Non-fatal contract validation
            for warning in _validate_plugin(name, instance):
                print(f"[dispatcher] ⚠ '{name}': {warning}")

            loaded.append((name, instance))

        loaded.sort(key=lambda x: getattr(x[1], "priority", 100))
        self._plugins = {name: inst for name, inst in loaded}

        ok  = list(self._plugins.keys())
        bad = list(self._failed_plugins.keys())
        print(f"[dispatcher] loaded ({len(ok)}): {ok}")
        if bad:
            print(f"[dispatcher] failed ({len(bad)}): {bad}")

    def reload_plugins(self) -> str:
        """Hot-reload all plugins without restarting Jarvis."""
        import importlib
        # Invalidate cached plugin modules so importlib picks up changes
        to_remove = [
            key for key in sys_modules_keys()
            if key.startswith("plugins.") and key != "plugins.base"
        ]
        import sys
        for key in to_remove:
            sys.modules.pop(key, None)

        self._plugins.clear()
        self._failed_plugins.clear()
        self._load_plugins()
        ok  = len(self._plugins)
        bad = len(self._failed_plugins)
        return f"Plugins reloaded — {ok} loaded, {bad} failed."

    # ------------------------------------------------------------------ #
    # Routing helpers
    # ------------------------------------------------------------------ #

    def _call(self, plugin_name: str, method: str, *args, **kwargs) -> str:
        """Call plugin.method safely, returning an error string on failure."""
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return f"[{plugin_name}] plugin not loaded."
        fn = getattr(plugin, method, None)
        if fn is None:
            return f"[{plugin_name}] method '{method}' not found."
        try:
            result = fn(*args, **kwargs)
            return result if isinstance(result, str) else str(result)
        except Exception as exc:
            tb = traceback.format_exc()
            print(f"[dispatcher] ✗ {plugin_name}.{method} raised:\n{tb}")
            return f"[{plugin_name}] error in {method}: {exc}"

    def _run(self, plugin_name: str, text: str, memory) -> str:
        """Call plugin.run() safely."""
        return self._call(plugin_name, "run", text, memory)

    # ------------------------------------------------------------------ #
    # Intent → plugin routing
    # ------------------------------------------------------------------ #

    def _route(self, intent: str, args: dict, text: str, memory) -> str:  # noqa: C901
        p = self._plugins

        # ── system ────────────────────────────────────────────────────────
        if intent == "system.stats"   and "system" in p: return self._call("system", "_stats", text)
        if intent == "system.uptime"  and "system" in p: return self._call("system", "_uptime", text)
        if intent == "system.sysinfo" and "system" in p: return self._call("system", "_sysinfo", text)
        if intent == "system.shell"   and "system" in p: return self._call("system", "_shell", f"run {args.get('cmd','')}")
        if intent == "system.open"    and "system" in p: return self._call("system", "_open", f"open {args.get('target','')}")
        if intent == "system.env"     and "system" in p: return self._call("system", "_env", f"env {args.get('key','')}")
        if intent == "system.setenv"  and "system" in p: return self._call("system", "_setenv", f"set env {args.get('key','')}={args.get('value','')}")

        # ── filesystem ────────────────────────────────────────────────────
        if intent == "fs.find"   and "filesystem" in p: return self._call("filesystem", "_find", f"find {args.get('pattern','')}")
        if intent == "fs.read"   and "filesystem" in p: return self._call("filesystem", "_read", f"read {args.get('path','')}")
        if intent == "fs.list"   and "filesystem" in p: return self._call("filesystem", "_list", f"list {args.get('path','.')}")
        if intent == "fs.move"   and "filesystem" in p: return self._call("filesystem", "_move", f"move {args.get('src','')} to {args.get('dst','')}")
        if intent == "fs.delete" and "filesystem" in p: return self._call("filesystem", "_delete", f"delete file {args.get('path','')}")
        if intent == "fs.mkdir"  and "filesystem" in p: return self._call("filesystem", "_mkdir", f"mkdir {args.get('path','')}")
        if intent == "fs.pwd"    and "filesystem" in p: return self._call("filesystem", "_pwd", text)

        # ── process ───────────────────────────────────────────────────────
        if intent == "process.list" and "process" in p: return self._call("process", "_list", text)
        if intent == "process.kill" and "process" in p: return self._call("process", "_kill", f"kill {args.get('target','')}")
        if intent == "process.find" and "process" in p: return self._call("process", "_find", f"find process {args.get('name','')}")

        # ── network ───────────────────────────────────────────────────────
        if intent == "net.ping"      and "network" in p: return self._call("network", "_ping", f"ping {args.get('host','')}")
        if intent == "net.curl"      and "network" in p: return self._call("network", "_curl", f"curl {args.get('url','')}")
        if intent == "net.download"  and "network" in p: return self._call("network", "_download", f"download {args.get('url','')}")
        if intent == "net.portscan"  and "network" in p: return self._call("network", "_portscan", f"port scan {args.get('host','')}")
        if intent == "net.myip"      and "network" in p: return self._call("network", "_myip", text)
        if intent == "net.ipinfo"    and "network" in p: return self._call("network", "_ipinfo", f"ip info {args.get('ip','')}")
        if intent == "net.dns"       and "network" in p: return self._call("network", "_dns", f"resolve {args.get('host','')}")
        if intent == "net.checkurl"  and "network" in p: return self._call("network", "_checkurl", f"check url {args.get('url','')}")
        if intent == "net.localip"   and "network" in p: return self._call("network", "_localip", text)
        if intent == "net.speedtest" and "network" in p: return self._call("network", "_speedtest", text)

        # ── web ───────────────────────────────────────────────────────────
        if "web" in p:
            if intent == "web.summarize": return self._call("web", "summarize", args.get("url",""), args.get("focus",""))
            if intent == "web.read"     : return self._call("web", "read", args.get("url",""))
            if intent == "web.ask"      : return self._call("web", "ask", args.get("url",""), args.get("question",""))
            if intent == "web.extract"  : return self._call("web", "extract", args.get("url",""), args.get("what",""))
            if intent == "web.compare"  : return self._call("web", "compare", args.get("url1",""), args.get("url2",""), args.get("aspect",""))
            if intent == "web.search"   : return self._call("web", "search", args.get("query",""))
            if intent == "web.news"     : return self._call("web", "news", args.get("topic",""))

        # ── clipboard ─────────────────────────────────────────────────────
        if intent == "clip.read"  and "clipboard" in p: return self._call("clipboard", "_read", text)
        if intent == "clip.write" and "clipboard" in p: return self._call("clipboard", "_write", f"copy to clipboard {args.get('content','')}")

        # ── notify ────────────────────────────────────────────────────────
        if intent == "notify.send" and "notify" in p: return self._call("notify", "_notify", "Jarvis", args.get("message",""))

        # ── scheduler ─────────────────────────────────────────────────────
        if "scheduler" in p:
            if intent == "scheduler.add":
                return self._call(
                    "scheduler", "add_structured",
                    delay_seconds=int(args.get("delay_seconds") or 60),
                    message=args.get("message", "Reminder!"),
                    repeat=args.get("repeat", ""),
                )
            if intent == "scheduler.add_at":
                import re as _re, time as _t
                ts = args.get("time_str", "")
                m  = _re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", ts.lower())
                fa = 0.0
                if m:
                    hr, mn = int(m.group(1)), int(m.group(2) or 0)
                    mer = m.group(3) or ""
                    if mer == "pm" and hr != 12: hr += 12
                    elif mer == "am" and hr == 12: hr = 0
                    now = _t.localtime()
                    fa  = _t.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                                     hr, mn, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
                    if fa < _t.time(): fa += 86400
                return self._call(
                    "scheduler", "add_structured",
                    delay_seconds=0,
                    message=args.get("message", "Reminder!"),
                    repeat=args.get("repeat", ""),
                    fire_at=fa or (_t.time() + 60),
                )
            if intent == "scheduler.list"      : return self._call("scheduler", "_list")
            if intent == "scheduler.cancel"    : return self._call("scheduler", "_cancel", f"cancel {args.get('id','')}")
            if intent == "scheduler.snooze"    : return self._call("scheduler", "_snooze", f"snooze reminder {args.get('id','')} in {args.get('delay_seconds',300)} seconds")
            if intent == "scheduler.reschedule": return self._call("scheduler", "_reschedule", f"reschedule reminder {args.get('id','')} at {args.get('time_str','')}")

        # ── todo ──────────────────────────────────────────────────────────
        if "todo" in p:
            if intent == "todo.add":
                pri_raw = args.get("priority", "medium")
                pri = _PRI_MAP.get(str(pri_raw).lower(), 2) if isinstance(pri_raw, str) else int(pri_raw)
                return self._call("todo", "add",
                    title=args.get("title", ""), priority=pri,
                    tags=args.get("tags", ""), due=args.get("due", ""),
                    project=args.get("project", ""))
            if intent == "todo.list"    : return self._call("todo", "list_todos", args.get("status",""), args.get("tag",""), args.get("project",""))
            if intent == "todo.complete": return self._call("todo", "complete", int(args.get("id",0)))
            if intent == "todo.start"   : return self._call("todo", "start", int(args.get("id",0)))
            if intent == "todo.block"   : return self._call("todo", "block", int(args.get("id",0)))
            if intent == "todo.reopen"  : return self._call("todo", "reopen", int(args.get("id",0)))
            if intent == "todo.delete"  : return self._call("todo", "delete", int(args.get("id",0)))
            if intent == "todo.search"  : return self._call("todo", "search", args.get("query",""))
            if intent == "todo.due"     : return self._call("todo", "due_today")
            if intent == "todo.stats"   : return self._call("todo", "stats")
            if intent == "todo.edit":
                pri_raw = args.get("priority", "")
                pri = _PRI_MAP.get(str(pri_raw).lower(), 0) if pri_raw else 0
                return self._call("todo", "edit",
                    todo_id=int(args.get("id", 0)), title=args.get("title", ""),
                    priority=pri, tags=args.get("tags", ""),
                    due=args.get("due", ""), project=args.get("project", ""))

        # ── notes ─────────────────────────────────────────────────────────
        if intent == "notes.save"    and "notes" in p: return self._call("notes", "_save", f"save note {args.get('content','')} #{args.get('tag','')}", memory)
        if intent == "notes.list"    and "notes" in p: return self._call("notes", "_list", f"show notes #{args.get('tag','')}", memory)
        if intent == "notes.search"  and "notes" in p: return self._call("notes", "_search", f"search note {args.get('query','')}", memory)
        if intent == "notes.delete"  and "notes" in p: return self._call("notes", "_delete", f"delete note {args.get('id','')}", memory)
        if intent == "notes.history" and "notes" in p: return self._call("notes", "_history", text, memory)
        if intent == "notes.forget"  and "notes" in p: return self._call("notes", "_forget", text, memory)

        # ── launcher ──────────────────────────────────────────────────────
        if intent == "launcher.workspace" and "launcher" in p: return self._call("launcher", "_launch_workspace", args.get("name",""))
        if intent == "launcher.list"      and "launcher" in p: return self._call("launcher", "_list_workspaces", text)

        # ── github ────────────────────────────────────────────────────────
        if "github" in p:
            if intent == "gh.list_repos"   : return self._call("github", "list_repos", int(args.get("limit",10)))
            if intent == "gh.get_repo"     : return self._call("github", "get_repo", args.get("repo",""))
            if intent == "gh.list_issues"  : return self._call("github", "list_issues", args.get("repo",""), args.get("state","open"))
            if intent == "gh.create_issue" : return self._call("github", "create_issue", args.get("repo",""), args.get("title",""), args.get("body",""))
            if intent == "gh.close_issue"  : return self._call("github", "close_issue", args.get("repo",""), int(args.get("number",0)))
            if intent == "gh.list_prs"     : return self._call("github", "list_prs", args.get("repo",""), args.get("state","open"))
            if intent == "gh.list_commits" : return self._call("github", "list_commits", args.get("repo",""), args.get("branch",""), int(args.get("limit",10)))
            if intent == "gh.list_branches": return self._call("github", "list_branches", args.get("repo",""))
            if intent == "gh.search_repos" : return self._call("github", "search_repos", args.get("query",""))

        # ── LLM fallback ──────────────────────────────────────────────────
        if "llm" in p:
            return self._run("llm", text, memory)

        return "I don't know how to handle that yet."

    # ------------------------------------------------------------------ #
    # Public dispatch entry point
    # ------------------------------------------------------------------ #

    def dispatch(self, text: str, memory) -> str:
        """Route text to the right plugin. Always returns a str."""
        if not text or not text.strip():
            return ""
        try:
            if not self._use_llm_routing:
                for _, plugin in self._plugins.items():
                    try:
                        if plugin.matches(text):
                            result = plugin.run(text, memory)
                            return result if isinstance(result, str) else str(result)
                    except Exception as exc:
                        name = type(plugin).__module__.split(".")[1] if "." in type(plugin).__module__ else "unknown"
                        print(f"[dispatcher] ✗ plugin '{name}' raised in keyword mode: {exc}")
                        continue
                return "No plugin matched."

            try:
                result = intent_router.classify(text)
            except Exception as exc:
                print(f"[dispatcher] intent_router failed: {exc}; falling back to keyword matching")
                for _, plugin in self._plugins.items():
                    try:
                        if plugin.matches(text):
                            return plugin.run(text, memory)
                    except Exception:
                        continue
                return "No plugin matched (intent router unavailable)."

            intent = result.get("intent", "llm.chat")
            args   = result.get("args", {})
            if not isinstance(args, dict):
                args = {}

            if get("debug", False):
                print(f"[router] intent={intent}  args={args}")

            return self._route(intent, args, text, memory)

        except Exception as exc:
            tb = traceback.format_exc()
            print(f"[dispatcher] Unhandled exception in dispatch():\n{tb}")
            return f"An internal error occurred: {exc}"


def sys_modules_keys():
    import sys
    return list(sys.modules.keys())
