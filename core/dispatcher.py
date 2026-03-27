"""Dispatcher — LLM intent routing → plugin method calls."""

import importlib
import pkgutil
import plugins as plugin_pkg
from plugins.base import PluginBase
from core import intent_router
from core.config import get

_PRI_MAP = {"low": 1, "medium": 2, "med": 2, "high": 3, "urgent": 4, "critical": 4}


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
                    loaded.append((name, cls()))
            except Exception as e:
                print(f"[dispatcher] failed to load '{name}': {e}")
        loaded.sort(key=lambda x: getattr(x[1], "priority", 100))
        self._plugins = {name: inst for name, inst in loaded}
        print(f"[dispatcher] loaded: {list(self._plugins.keys())}")

    def _route(self, intent: str, args: dict, text: str, memory) -> str:
        p = self._plugins

        if intent == "system.stats"   and "system" in p: return p["system"]._stats(text)
        if intent == "system.uptime"  and "system" in p: return p["system"]._uptime(text)
        if intent == "system.sysinfo" and "system" in p: return p["system"]._sysinfo(text)
        if intent == "system.shell"   and "system" in p: return p["system"]._shell(f"run {args.get('cmd','')}")
        if intent == "system.open"    and "system" in p: return p["system"]._open(f"open {args.get('target','')}")
        if intent == "system.env"     and "system" in p: return p["system"]._env(f"env {args.get('key','')}")
        if intent == "system.setenv"  and "system" in p: return p["system"]._setenv(f"set env {args.get('key','')}={args.get('value','')}")

        if intent == "fs.find"   and "filesystem" in p: return p["filesystem"]._find(f"find {args.get('pattern','')}")
        if intent == "fs.read"   and "filesystem" in p: return p["filesystem"]._read(f"read {args.get('path','')}")
        if intent == "fs.list"   and "filesystem" in p: return p["filesystem"]._list(f"list {args.get('path','.')}")
        if intent == "fs.move"   and "filesystem" in p: return p["filesystem"]._move(f"move {args.get('src','')} to {args.get('dst','')}")
        if intent == "fs.delete" and "filesystem" in p: return p["filesystem"]._delete(f"delete file {args.get('path','')}")
        if intent == "fs.mkdir"  and "filesystem" in p: return p["filesystem"]._mkdir(f"mkdir {args.get('path','')}")
        if intent == "fs.pwd"    and "filesystem" in p: return p["filesystem"]._pwd(text)

        if intent == "process.list" and "process" in p: return p["process"]._list(text)
        if intent == "process.kill" and "process" in p: return p["process"]._kill(f"kill {args.get('target','')}")
        if intent == "process.find" and "process" in p: return p["process"]._find(f"find process {args.get('name','')}")

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

        if "web" in p:
            wb = p["web"]
            if intent == "web.summarize": return wb.summarize(args.get("url",""), args.get("focus",""))
            if intent == "web.read"     : return wb.read(args.get("url",""))
            if intent == "web.ask"      : return wb.ask(args.get("url",""), args.get("question",""))
            if intent == "web.extract"  : return wb.extract(args.get("url",""), args.get("what",""))
            if intent == "web.compare"  : return wb.compare(args.get("url1",""), args.get("url2",""), args.get("aspect",""))
            if intent == "web.search"   : return wb.search(args.get("query",""))
            if intent == "web.news"     : return wb.news(args.get("topic",""))

        if intent == "clip.read"  and "clipboard" in p: return p["clipboard"]._read(text)
        if intent == "clip.write" and "clipboard" in p: return p["clipboard"]._write(f"copy to clipboard {args.get('content','')}")
        if intent == "notify.send" and "notify" in p  : return p["notify"]._notify("Jarvis", args.get("message",""))

        # scheduler v2
        if "scheduler" in p:
            sch = p["scheduler"]
            if intent == "scheduler.add":
                return sch.add_structured(
                    delay_seconds=int(args.get("delay_seconds") or 60),
                    message=args.get("message", "Reminder!"),
                    repeat=args.get("repeat", ""),
                )
            if intent == "scheduler.add_at":
                import re, time as _t
                ts  = args.get("time_str", "")
                # parse HH:MM am/pm from time_str
                m   = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", ts.lower())
                fa  = 0.0
                if m:
                    hr  = int(m.group(1))
                    mn  = int(m.group(2) or 0)
                    mer = m.group(3) or ""
                    if mer == "pm" and hr != 12: hr += 12
                    elif mer == "am" and hr == 12: hr = 0
                    now = _t.localtime()
                    fa  = _t.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                                     hr, mn, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
                    if fa < _t.time(): fa += 86400
                return sch.add_structured(
                    delay_seconds=0,
                    message=args.get("message", "Reminder!"),
                    repeat=args.get("repeat", ""),
                    fire_at=fa or (_t.time() + 60),
                )
            if intent == "scheduler.list"      : return sch._list()
            if intent == "scheduler.cancel"    : return sch._cancel(f"cancel {args.get('id','')}")
            if intent == "scheduler.snooze"    : return sch._snooze(f"snooze reminder {args.get('id','')} in {args.get('delay_seconds',300)} seconds")
            if intent == "scheduler.reschedule": return sch._reschedule(f"reschedule reminder {args.get('id','')} at {args.get('time_str','')}")

        # todo
        if "todo" in p:
            td = p["todo"]
            if intent == "todo.add":
                pri_raw = args.get("priority", "medium")
                pri     = _PRI_MAP.get(str(pri_raw).lower(), 2) if isinstance(pri_raw, str) else int(pri_raw)
                return td.add(
                    title   = args.get("title", ""),
                    priority= pri,
                    tags    = args.get("tags", ""),
                    due     = args.get("due", ""),
                    project = args.get("project", ""),
                )
            if intent == "todo.list"    : return td.list_todos(args.get("status",""), args.get("tag",""), args.get("project",""))
            if intent == "todo.complete": return td.complete(int(args.get("id",0)))
            if intent == "todo.start"   : return td.start(int(args.get("id",0)))
            if intent == "todo.block"   : return td.block(int(args.get("id",0)))
            if intent == "todo.reopen"  : return td.reopen(int(args.get("id",0)))
            if intent == "todo.delete"  : return td.delete(int(args.get("id",0)))
            if intent == "todo.search"  : return td.search(args.get("query",""))
            if intent == "todo.due"     : return td.due_today()
            if intent == "todo.stats"   : return td.stats()
            if intent == "todo.edit":
                pri_raw = args.get("priority", "")
                pri     = _PRI_MAP.get(str(pri_raw).lower(), 0) if pri_raw else 0
                return td.edit(
                    todo_id = int(args.get("id", 0)),
                    title   = args.get("title", ""),
                    priority= pri,
                    tags    = args.get("tags", ""),
                    due     = args.get("due", ""),
                    project = args.get("project", ""),
                )

        if intent == "notes.save"    and "notes" in p: return p["notes"]._save(f"save note {args.get('content','')} #{args.get('tag','')}", memory)
        if intent == "notes.list"    and "notes" in p: return p["notes"]._list(f"show notes #{args.get('tag','')}", memory)
        if intent == "notes.search"  and "notes" in p: return p["notes"]._search(f"search note {args.get('query','')}", memory)
        if intent == "notes.delete"  and "notes" in p: return p["notes"]._delete(f"delete note {args.get('id','')}", memory)
        if intent == "notes.history" and "notes" in p: return p["notes"]._history(text, memory)
        if intent == "notes.forget"  and "notes" in p: return p["notes"]._forget(text, memory)

        if intent == "launcher.workspace" and "launcher" in p: return p["launcher"]._launch_workspace(args.get("name",""))
        if intent == "launcher.list"      and "launcher" in p: return p["launcher"]._list_workspaces(text)

        if "github" in p:
            gh = p["github"]
            if intent == "gh.list_repos"   : return gh.list_repos(int(args.get("limit",10)))
            if intent == "gh.get_repo"     : return gh.get_repo(args.get("repo",""))
            if intent == "gh.list_issues"  : return gh.list_issues(args.get("repo",""), args.get("state","open"))
            if intent == "gh.create_issue" : return gh.create_issue(args.get("repo",""), args.get("title",""), args.get("body",""))
            if intent == "gh.close_issue"  : return gh.close_issue(args.get("repo",""), int(args.get("number",0)))
            if intent == "gh.list_prs"     : return gh.list_prs(args.get("repo",""), args.get("state","open"))
            if intent == "gh.list_commits" : return gh.list_commits(args.get("repo",""), args.get("branch",""), int(args.get("limit",10)))
            if intent == "gh.list_branches": return gh.list_branches(args.get("repo",""))
            if intent == "gh.search_repos" : return gh.search_repos(args.get("query",""))

        if "llm" in p: return p["llm"].run(text, memory)
        return "No handler found."

    def dispatch(self, text: str, memory) -> str:
        if not self._use_llm_routing:
            for _, plugin in self._plugins.items():
                if plugin.matches(text):
                    return plugin.run(text, memory)
            return "No plugin matched."
        result = intent_router.classify(text)
        intent = result.get("intent", "llm.chat")
        args   = result.get("args", {})
        if get("debug", False):
            print(f"[router] intent={intent}  args={args}")
        return self._route(intent, args, text, memory)
