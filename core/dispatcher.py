"""Dispatcher — LLM-powered intent routing with plugin fallback.

Flow:
  user input
    └→ intent_router.classify()   (fast LLM call, temp=0, max_tokens=150)
        └→ route to plugin handler via intent map
            └→ if llm.chat or unmatched → LLM plugin (full response)
"""

import importlib
import pkgutil
import plugins as plugin_pkg
from plugins.base import PluginBase
from core import intent_router
from core.config import get


class Dispatcher:
    def __init__(self):
        self._plugins: dict[str, PluginBase] = {}
        self._load_plugins()
        self._use_llm_routing = get("llm_routing", True)

    def _load_plugins(self):
        loaded = []
        for _, name, _ in pkgutil.iter_modules(plugin_pkg.__path__):
            if name == "base":
                continue
            try:
                mod = importlib.import_module(f"plugins.{name}.plugin")
                cls = getattr(mod, "Plugin", None)
                if cls and issubclass(cls, PluginBase):
                    inst = cls()
                    loaded.append((name, inst))
            except Exception as e:
                print(f"[dispatcher] failed to load '{name}': {e}")
        loaded.sort(key=lambda x: getattr(x[1], "priority", 100))
        self._plugins = {name: inst for name, inst in loaded}
        print(f"[dispatcher] loaded: {list(self._plugins.keys())}")

    # ── intent → plugin method map ─────────────────────────────────────

    def _route(self, intent: str, args: dict, text: str, memory) -> str:
        p = self._plugins

        # system
        if intent == "system.stats"   and "system" in p: return p["system"]._stats(text)
        if intent == "system.uptime"  and "system" in p: return p["system"]._uptime(text)
        if intent == "system.sysinfo" and "system" in p: return p["system"]._sysinfo(text)
        if intent == "system.shell"   and "system" in p: return p["system"]._shell(f"run {args.get('cmd','')}")
        if intent == "system.open"    and "system" in p: return p["system"]._open(f"open {args.get('target','')}")
        if intent == "system.env"     and "system" in p: return p["system"]._env(f"env {args.get('key','')}")
        if intent == "system.setenv"  and "system" in p: return p["system"]._setenv(f"set env {args.get('key','')}={args.get('value','')}")

        # filesystem
        if intent == "fs.find"   and "filesystem" in p: return p["filesystem"]._find(f"find {args.get('pattern','')}")
        if intent == "fs.read"   and "filesystem" in p: return p["filesystem"]._read(f"read {args.get('path','')}")
        if intent == "fs.list"   and "filesystem" in p: return p["filesystem"]._list(f"list {args.get('path','.')}")
        if intent == "fs.move"   and "filesystem" in p: return p["filesystem"]._move(f"move {args.get('src','')} to {args.get('dst','')}")
        if intent == "fs.delete" and "filesystem" in p: return p["filesystem"]._delete(f"delete file {args.get('path','')}")
        if intent == "fs.mkdir"  and "filesystem" in p: return p["filesystem"]._mkdir(f"mkdir {args.get('path','')}")
        if intent == "fs.pwd"    and "filesystem" in p: return p["filesystem"]._pwd(text)

        # process
        if intent == "process.list" and "process" in p: return p["process"]._list(text)
        if intent == "process.kill" and "process" in p: return p["process"]._kill(f"kill {args.get('target','')}")
        if intent == "process.find" and "process" in p: return p["process"]._find(f"find process {args.get('name','')}")

        # network
        if intent == "net.ping"      and "network" in p: return p["network"]._ping(f"ping {args.get('host','')}")
        if intent == "net.curl"      and "network" in p: return p["network"]._curl(f"curl {args.get('url','')}")
        if intent == "net.download"  and "network" in p: return p["network"]._download(f"download {args.get('url','')}")
        if intent == "net.portscan"  and "network" in p: return p["network"]._portscan(f"port scan {args.get('host','')}")
        if intent == "net.myip"      and "network" in p: return p["network"]._myip(text)
        if intent == "net.ipinfo"    and "network" in p: return p["network"]._ipinfo(f"ip info {args.get('ip','')}")
        if intent == "net.dns"       and "network" in p: return p["network"]._dns(f"resolve {args.get('host','')}")
        if intent == "net.checkurl"  and "network" in p: return p["network"]._checkurl(f"check url {args.get('url','')}")
        if intent == "net.localip"   and "network" in p: return p["network"]._localip(text)
        if intent == "net.speedtest" and "network" in p: return p["network"]._speedtest(text)

        # clipboard
        if intent == "clip.read"  and "clipboard" in p: return p["clipboard"]._read(text)
        if intent == "clip.write" and "clipboard" in p: return p["clipboard"]._write(f"copy to clipboard {args.get('content','')}")

        # notify
        if intent == "notify.send" and "notify" in p: return p["notify"]._notify("Jarvis", args.get("message", ""))

        # scheduler
        if intent == "scheduler.add" and "scheduler" in p:
            import time, sqlite3, os
            delay   = int(args.get("delay_seconds", 60))
            message = args.get("message", "Reminder!")
            repeat  = args.get("repeat", "")
            fire_at = time.time() + delay
            sch = p["scheduler"]
            con = sqlite3.connect(sch._db_path)
            cur = con.execute("INSERT INTO reminders (fire_at, message, repeat) VALUES (?,?,?)",
                              (fire_at, message, repeat))
            rid = cur.lastrowid
            con.commit(); con.close()
            when = time.strftime("%H:%M:%S", time.localtime(fire_at))
            return f"Reminder #{rid} set for {when}{' repeats '+repeat if repeat else ''}: {message}"
        if intent == "scheduler.list"   and "scheduler" in p: return p["scheduler"]._list()
        if intent == "scheduler.cancel" and "scheduler" in p: return p["scheduler"]._cancel(f"cancel reminder {args.get('id','')}")

        # notes
        if intent == "notes.save"    and "notes" in p: return p["notes"]._save(f"save note {args.get('content','')} #{args.get('tag','')}", memory)
        if intent == "notes.list"    and "notes" in p: return p["notes"]._list(f"show notes #{args.get('tag','')}", memory)
        if intent == "notes.search"  and "notes" in p: return p["notes"]._search(f"search note {args.get('query','')}", memory)
        if intent == "notes.delete"  and "notes" in p: return p["notes"]._delete(f"delete note {args.get('id','')}", memory)
        if intent == "notes.history" and "notes" in p: return p["notes"]._history(text, memory)
        if intent == "notes.forget"  and "notes" in p: return p["notes"]._forget(text, memory)

        # launcher
        if intent == "launcher.workspace" and "launcher" in p: return p["launcher"]._launch_workspace(args.get("name", ""))
        if intent == "launcher.list"      and "launcher" in p: return p["launcher"]._list_workspaces(text)

        # fallback → LLM full response
        if "llm" in p:
            return p["llm"].run(text, memory)
        return "No handler found."

    # ── main dispatch ────────────────────────────────────────────────────────────

    def dispatch(self, text: str, memory) -> str:
        if not self._use_llm_routing:
            # Legacy keyword mode
            for _, plugin in self._plugins.items():
                if plugin.matches(text):
                    return plugin.run(text, memory)
            return "No plugin matched."

        result = intent_router.classify(text)
        intent = result.get("intent", "llm.chat")
        args   = result.get("args", {})
        debug  = __import__("core.config", fromlist=["get"]).get("debug", False)
        if debug:
            print(f"[router] intent={intent}  args={args}")
        return self._route(intent, args, text, memory)
