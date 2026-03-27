"""Intent Router v5 — pre-classifier + auto-discovery edition.

Flow
----
1. Dispatcher calls intent_router.register(registry) after loading plugins.
   This injects the auto-discovered intents into the router's schema.
2. Every user input first goes through the keyword pre-classifier.
   If matched, the LLM is skipped entirely.
3. If no keyword match, the LLM returns:
     {"intent": "<id>", "args": {...}, "trigger": "<canonical phrase>"}
4. The dispatcher routes by intent to the right plugin via PluginRegistry.

No manual INTENT_SCHEMA or TRIGGER_MAP entries needed for new plugins.
Just add PluginCapability objects to your Plugin class.
"""

import re
import json
import urllib.request
import urllib.error
from core.config import get_llm_config

# ---------------------------------------------------------------------------
# Core built-in intents that have no dedicated plugin file
# ---------------------------------------------------------------------------
_BUILTIN_SCHEMA: dict[str, dict] = {
    "system.stats"        : {},
    "system.uptime"       : {},
    "system.sysinfo"      : {},
    "system.shell"        : {"cmd": "str"},
    "system.open"         : {"target": "str"},
    "system.env"          : {"key": "str?"},
    "system.setenv"       : {"key": "str", "value": "str"},
    "system.services"     : {},
    "system.battery"      : {},
    "system.reboot"       : {},
    "system.shutdown"     : {},
    "fs.find"             : {"pattern": "str"},
    "fs.read"             : {"path": "str"},
    "fs.write"            : {"path": "str", "content": "str"},
    "fs.list"             : {"path": "str?"},
    "fs.move"             : {"src": "str", "dst": "str"},
    "fs.delete"           : {"path": "str"},
    "fs.mkdir"            : {"path": "str"},
    "fs.pwd"              : {},
    "fs.copy"             : {"src": "str", "dst": "str"},
    "fs.stat"             : {"path": "str"},
    "fs.tree"             : {"path": "str?"},
    "fs.diskusage"        : {"path": "str?"},
    "process.list"        : {},
    "process.kill"        : {"target": "str"},
    "process.find"        : {"name": "str"},
    "process.top"         : {"limit": "int?"},
    "process.suspend"     : {"target": "str"},
    "process.resume"      : {"target": "str"},
    "net.ping"            : {"host": "str"},
    "net.curl"            : {"url": "str"},
    "net.download"        : {"url": "str"},
    "net.portscan"        : {"host": "str"},
    "net.myip"            : {},
    "net.ipinfo"          : {"ip": "str"},
    "net.dns"             : {"host": "str"},
    "net.checkurl"        : {"url": "str"},
    "net.localip"         : {},
    "net.speedtest"       : {},
    "net.traceroute"      : {"host": "str"},
    "net.headers"         : {"url": "str"},
    "net.interfaces"      : {},
    "nmap.scan_normal"    : {"target": "str"},
    "nmap.scan_silent"    : {"target": "str"},
    "nmap.scan_full"      : {"target": "str"},
    "nmap.scan_version"   : {"target": "str"},
    "nmap.scan_os"        : {"target": "str"},
    "nmap.scan_vuln"      : {"target": "str"},
    "nmap.scan_quick"     : {"target": "str"},
    "web.summarize"       : {"url": "str", "focus": "str?"},
    "web.read"            : {"url": "str"},
    "web.ask"             : {"url": "str", "question": "str"},
    "web.extract"         : {"url": "str", "what": "str"},
    "web.compare"         : {"url1": "str", "url2": "str", "aspect": "str?"},
    "web.search"          : {"query": "str"},
    "web.news"            : {"topic": "str"},
    "clip.read"           : {},
    "clip.write"          : {"content": "str"},
    "notify.send"         : {"message": "str"},
    "scheduler.add"       : {"delay_seconds": "int?", "message": "str", "repeat": "str?"},
    "scheduler.add_at"    : {"time_str": "str", "message": "str", "repeat": "str?"},
    "scheduler.list"      : {},
    "scheduler.cancel"    : {"id": "int"},
    "scheduler.snooze"    : {"id": "int", "delay_seconds": "int?"},
    "scheduler.reschedule": {"id": "int", "time_str": "str"},
    "todo.add"            : {"title": "str", "priority": "str?", "tags": "str?", "due": "str?", "project": "str?"},
    "todo.list"           : {"status": "str?", "tag": "str?", "project": "str?"},
    "todo.complete"       : {"id": "int"},
    "todo.start"          : {"id": "int"},
    "todo.block"          : {"id": "int"},
    "todo.reopen"         : {"id": "int"},
    "todo.delete"         : {"id": "int"},
    "todo.edit"           : {"id": "int", "title": "str?", "priority": "str?", "due": "str?", "tags": "str?", "project": "str?"},
    "todo.search"         : {"query": "str"},
    "todo.due"            : {},
    "todo.stats"          : {},
    "notes.save"          : {"content": "str", "tag": "str?"},
    "notes.list"          : {"tag": "str?"},
    "notes.search"        : {"query": "str"},
    "notes.delete"        : {"id": "int"},
    "notes.history"       : {},
    "notes.forget"        : {},
    "launcher.workspace"  : {"name": "str"},
    "launcher.list"       : {},
    "gh.list_repos"       : {"limit": "int?"},
    "gh.get_repo"         : {"repo": "str"},
    "gh.list_issues"      : {"repo": "str", "state": "str?"},
    "gh.create_issue"     : {"repo": "str", "title": "str", "body": "str?"},
    "gh.close_issue"      : {"repo": "str", "number": "int"},
    "gh.list_prs"         : {"repo": "str", "state": "str?"},
    "gh.list_commits"     : {"repo": "str", "branch": "str?", "limit": "int?"},
    "gh.list_branches"    : {"repo": "str"},
    "gh.search_repos"     : {"query": "str"},
    "brightness.get"      : {},
    "brightness.set"      : {"level": "int"},
    "brightness.up"       : {},
    "brightness.down"     : {},
    "stopwatch.start"     : {"name": "str?"},
    "stopwatch.stop"      : {"name": "str?"},
    "stopwatch.pause"     : {"name": "str?"},
    "stopwatch.resume"    : {"name": "str?"},
    "stopwatch.lap"       : {"name": "str?"},
    "stopwatch.elapsed"   : {"name": "str?"},
    "stopwatch.list"      : {},
    "stopwatch.reset"     : {"name": "str?"},
    "env.get"             : {"key": "str"},
    "env.set"             : {"key": "str", "value": "str"},
    "env.unset"           : {"key": "str"},
    "env.list"            : {},
    "env.search"          : {"keyword": "str"},
    "clip_history.list"   : {"limit": "int?"},
    "clip_history.search" : {"keyword": "str"},
    "clip_history.recopy" : {"index": "int"},
    "clip_history.clear"  : {},
    "llm.chat"            : {},
}

_BUILTIN_TRIGGERS: dict[str, str] = {
    "system.stats"        : "system stats",
    "system.uptime"       : "system uptime",
    "system.sysinfo"      : "system info",
    "system.shell"        : "run {cmd}",
    "system.open"         : "open {target}",
    "system.env"          : "env {key}",
    "system.setenv"       : "set env {key}={value}",
    "system.services"     : "list services",
    "system.battery"      : "battery status",
    "system.reboot"       : "reboot system",
    "system.shutdown"     : "shutdown system",
    "fs.find"             : "find {pattern}",
    "fs.read"             : "read {path}",
    "fs.write"            : "write {path}",
    "fs.list"             : "list {path}",
    "fs.move"             : "move {src} to {dst}",
    "fs.delete"           : "delete file {path}",
    "fs.mkdir"            : "mkdir {path}",
    "fs.pwd"              : "current directory",
    "fs.copy"             : "copy {src} to {dst}",
    "fs.stat"             : "stat {path}",
    "fs.tree"             : "tree {path}",
    "fs.diskusage"        : "disk usage {path}",
    "process.list"        : "list processes",
    "process.kill"        : "kill {target}",
    "process.find"        : "find process {name}",
    "process.top"         : "top processes",
    "process.suspend"     : "suspend {target}",
    "process.resume"      : "resume {target}",
    "net.ping"            : "ping {host}",
    "net.myip"            : "my public ip",
    "net.localip"         : "my local ip",
    "net.speedtest"       : "speed test",
    "net.dns"             : "dns {host}",
    "net.checkurl"        : "check url {url}",
    "net.download"        : "download {url}",
    "net.traceroute"      : "traceroute {host}",
    "net.headers"         : "headers {url}",
    "net.interfaces"      : "network interfaces",
    "nmap.scan_normal"    : "nmap scan {target}",
    "nmap.scan_silent"    : "nmap silent scan {target}",
    "nmap.scan_full"      : "nmap full scan {target}",
    "nmap.scan_version"   : "nmap version scan {target}",
    "nmap.scan_os"        : "nmap os scan {target}",
    "nmap.scan_vuln"      : "nmap vuln scan {target}",
    "nmap.scan_quick"     : "nmap quick scan {target}",
    "web.search"          : "search {query}",
    "web.news"            : "news {topic}",
    "web.summarize"       : "summarize {url}",
    "clip.read"           : "read clipboard",
    "clip.write"          : "copy to clipboard {content}",
    "notify.send"         : "notify {message}",
    "scheduler.add"       : "remind me in {delay_seconds} seconds {message}",
    "scheduler.add_at"    : "remind me at {time_str} {message}",
    "scheduler.list"      : "show reminders",
    "scheduler.cancel"    : "cancel reminder {id}",
    "todo.add"            : "add todo {title}",
    "todo.list"           : "list todos",
    "todo.complete"       : "complete todo {id}",
    "todo.delete"         : "delete todo {id}",
    "todo.search"         : "search todos {query}",
    "todo.due"            : "todos due today",
    "todo.stats"          : "todo stats",
    "notes.save"          : "save note {content}",
    "notes.list"          : "show notes",
    "notes.search"        : "search note {query}",
    "notes.delete"        : "delete note {id}",
    "launcher.workspace"  : "open workspace {name}",
    "launcher.list"       : "list workspaces",
    "gh.list_repos"       : "list repos",
    "gh.list_issues"      : "list issues {repo}",
    "gh.create_issue"     : "create issue {repo} {title}",
    "gh.list_prs"         : "list prs {repo}",
    "gh.list_commits"     : "list commits {repo}",
    "gh.search_repos"     : "search repos {query}",
    "brightness.get"      : "what is brightness",
    "brightness.set"      : "brightness set {level}",
    "brightness.up"       : "brightness up",
    "brightness.down"     : "brightness down",
    "stopwatch.start"     : "start stopwatch {name}",
    "stopwatch.stop"      : "stop stopwatch {name}",
    "stopwatch.pause"     : "pause stopwatch {name}",
    "stopwatch.resume"    : "resume stopwatch {name}",
    "stopwatch.lap"       : "lap stopwatch {name}",
    "stopwatch.elapsed"   : "elapsed stopwatch {name}",
    "stopwatch.list"      : "list stopwatches",
    "stopwatch.reset"     : "reset stopwatch {name}",
    "env.get"             : "env {key}",
    "env.set"             : "set env {key}={value}",
    "env.unset"           : "unset env {key}",
    "env.list"            : "list env",
    "env.search"          : "search env {keyword}",
    "clip_history.list"   : "clipboard history",
    "clip_history.search" : "clipboard search {keyword}",
    "clip_history.recopy" : "copy history item {index}",
    "clip_history.clear"  : "clear clipboard history",
    "llm.chat"            : "",
}

INTENT_SCHEMA: dict[str, dict] = dict(_BUILTIN_SCHEMA)
TRIGGER_MAP  : dict[str, str]  = dict(_BUILTIN_TRIGGERS)

_REQUIRED: dict[str, list] = {}
_DYNAMIC_EXAMPLES: list[tuple] = []


# ---------------------------------------------------------------------------
# Keyword pre-classifier
# Catches the most common commands before the LLM is called.
# Each rule is (regex_pattern, intent, args_fn).
# args_fn receives the re.Match object and returns a dict.
# Rules are evaluated top-to-bottom; first match wins.
# ---------------------------------------------------------------------------

def _url_from(m: re.Match, group: int = 1) -> str:
    raw = m.group(group).strip()
    if raw and not raw.startswith("http"):
        raw = "https://" + raw
    return raw


_PRE_RULES: list[tuple] = [
    # --- process ---
    (r"^(list|show|display)\s+(all\s+)?processes?$",
     "process.list", lambda m: {}),
    (r"^(list|show|display)\s+(all\s+)?running\s+processes?$",
     "process.list", lambda m: {}),
    (r"^(top|top\s+(\d+))\s+processes?",
     "process.top", lambda m: {"limit": int(m.group(2)) if m.group(2) else 10}),
    (r"^kill\s+(.+)$",
     "process.kill", lambda m: {"target": m.group(1).strip()}),
    (r"^(find|search)\s+process\s+(.+)$",
     "process.find", lambda m: {"name": m.group(2).strip()}),

    # --- filesystem ---
    (r"^(list|ls|show)\s+(files?\s+)?(?:from|in|at)?\s+(.+)$",
     "fs.list", lambda m: {"path": m.group(3).strip()}),
    (r"^(list|ls)\s*$",
     "fs.list", lambda m: {}),
    (r"^read\s+(file\s+)?(.+)$",
     "fs.read", lambda m: {"path": m.group(2).strip()}),
    (r"^(tree|show tree)\s*(.*)$",
     "fs.tree", lambda m: {"path": m.group(2).strip() or "."}),
    (r"^(disk\s*usage|du)\s*(.*)$",
     "fs.diskusage", lambda m: {"path": m.group(2).strip() or "."}),
    (r"^(stat|info)\s+(.+)$",
     "fs.stat", lambda m: {"path": m.group(2).strip()}),
    (r"^(pwd|current\s+dir(?:ectory)?)$",
     "fs.pwd", lambda m: {}),
    (r"^(find|search)\s+files?\s+(.+)$",
     "fs.find", lambda m: {"pattern": m.group(2).strip()}),
    (r"^mkdir\s+(.+)$",
     "fs.mkdir", lambda m: {"path": m.group(1).strip()}),
    (r"^(delete|remove|rm)\s+(file\s+)?(.+)$",
     "fs.delete", lambda m: {"path": m.group(3).strip()}),

    # --- network ---
    (r"^ping\s+(.+)$",
     "net.ping", lambda m: {"host": m.group(1).strip()}),
    (r"^(check|is|test)\s+(.+?)\s+(working|up|down|online|reachable)\??$",
     "net.checkurl", lambda m: {"url": _url_from(m, 2)}),
    (r"^(check\s+url|checkurl)\s+(.+)$",
     "net.checkurl", lambda m: {"url": _url_from(m, 2)}),
    (r"^(my\s+)?(public\s+)?ip(\s+address)?$",
     "net.myip", lambda m: {}),
    (r"^(my\s+)?local\s+ip(\s+address)?$",
     "net.localip", lambda m: {}),
    (r"^(speed\s*test|test\s+(my\s+)?speed)$",
     "net.speedtest", lambda m: {}),
    (r"^(dns|nslookup)\s+(.+)$",
     "net.dns", lambda m: {"host": m.group(2).strip()}),
    (r"^(traceroute|tracert)\s+(.+)$",
     "net.traceroute", lambda m: {"host": m.group(2).strip()}),
    (r"^(headers|http\s+headers)\s+(.+)$",
     "net.headers", lambda m: {"url": _url_from(m, 2)}),
    (r"^(network\s+)?(interfaces?|adapters?)$",
     "net.interfaces", lambda m: {}),
    (r"^(download|fetch)\s+(.+)$",
     "net.download", lambda m: {"url": _url_from(m, 2)}),
    (r"^curl\s+(.+)$",
     "net.curl", lambda m: {"url": _url_from(m, 1)}),

    # --- nmap ---
    (r"^(nmap\s+)?(scan|nmap)\s+(--vuln|-sV|--full|-sn)?\s*(.+)$",
     "nmap.scan_normal", lambda m: {"target": m.group(4).strip()}),
    (r"^(full|deep)\s+scan\s+(.+)$",
     "nmap.scan_full", lambda m: {"target": m.group(2).strip()}),
    (r"^(vuln|vulnerability)\s+scan\s+(.+)$",
     "nmap.scan_vuln", lambda m: {"target": m.group(2).strip()}),
    (r"^(os|os\s+detect(?:ion)?)\s+scan\s+(.+)$",
     "nmap.scan_os", lambda m: {"target": m.group(2).strip()}),
    (r"^(version|service)\s+scan\s+(.+)$",
     "nmap.scan_version", lambda m: {"target": m.group(2).strip()}),
    (r"^(silent|stealth|quiet)\s+scan\s+(.+)$",
     "nmap.scan_silent", lambda m: {"target": m.group(2).strip()}),
    (r"^(quick)\s+scan\s+(.+)$",
     "nmap.scan_quick", lambda m: {"target": m.group(2).strip()}),

    # --- system ---
    (r"^(system\s+)?(stats?|status|usage)$",
     "system.stats", lambda m: {}),
    (r"^(system\s+)?uptime$",
     "system.uptime", lambda m: {}),
    (r"^(system\s+)?(info|sysinfo|system\s+information)$",
     "system.sysinfo", lambda m: {}),
    (r"^(list\s+)?services?$",
     "system.services", lambda m: {}),
    (r"^battery(\s+status)?$",
     "system.battery", lambda m: {}),
    (r"^(run|exec|execute|shell)\s+(.+)$",
     "system.shell", lambda m: {"cmd": m.group(2).strip()}),
    (r"^(open|launch|start)\s+(.+)$",
     "system.open", lambda m: {"target": m.group(2).strip()}),
]

# Compile all patterns once at import time
_PRE_RULES_COMPILED = [
    (re.compile(pattern, re.IGNORECASE), intent, args_fn)
    for pattern, intent, args_fn in _PRE_RULES
]


def _keyword_classify(text: str) -> dict | None:
    """
    Try to match user input against keyword rules.
    Returns a classified dict if matched, None otherwise.
    """
    stripped = text.strip()
    for pattern, intent, args_fn in _PRE_RULES_COMPILED:
        m = pattern.match(stripped)
        if m:
            try:
                args = args_fn(m)
            except Exception:
                args = {}
            trigger = TRIGGER_MAP.get(intent, intent)
            try:
                trigger = trigger.format_map(args)
            except KeyError:
                pass
            return {"intent": intent, "args": args, "trigger": trigger, "_source": "keyword"}
    return None


# ---------------------------------------------------------------------------
# Plugin registry merge
# ---------------------------------------------------------------------------
def register(registry) -> None:
    global _REQUIRED, _DYNAMIC_EXAMPLES, _CACHED_PROMPT

    INTENT_SCHEMA.update(registry.intent_schema)
    TRIGGER_MAP.update(registry.trigger_map)
    _DYNAMIC_EXAMPLES = registry.examples

    _REQUIRED = {
        k: [a for a, t in v.items() if not t.endswith("?")]
        for k, v in INTENT_SCHEMA.items()
    }
    _CACHED_PROMPT = None
    print(f"[router] registered {len(registry.intent_schema)} plugin-declared intents")


# ---------------------------------------------------------------------------
# Built-in few-shot examples
# ---------------------------------------------------------------------------
_BUILTIN_EXAMPLES = [
    ("how much ram am i using",
     '{"intent":"system.stats","args":{},"trigger":"system stats"}'),
    ("run git status",
     '{"intent":"system.shell","args":{"cmd":"git status"},"trigger":"run git status"}'),
    ("kill chrome",
     '{"intent":"process.kill","args":{"target":"chrome"},"trigger":"kill chrome"}'),
    ("is github down",
     '{"intent":"net.checkurl","args":{"url":"https://github.com"},"trigger":"check url https://github.com"}'),
    ("latest news on AI",
     '{"intent":"web.news","args":{"topic":"AI"},"trigger":"news AI"}'),
    ("remind me in 10 minutes to call John",
     '{"intent":"scheduler.add","args":{"delay_seconds":600,"message":"call John"},"trigger":"remind me in 600 seconds call John"}'),
    ("add todo fix the login bug high priority",
     '{"intent":"todo.add","args":{"title":"fix the login bug","priority":"high"},"trigger":"add todo fix the login bug"}'),
    ("show my todos",
     '{"intent":"todo.list","args":{},"trigger":"list todos"}'),
    ("list all running processes",
     '{"intent":"process.list","args":{},"trigger":"list processes"}'),
    ("scan eyeqdotnet.com",
     '{"intent":"nmap.scan_normal","args":{"target":"eyeqdotnet.com"},"trigger":"nmap scan eyeqdotnet.com"}'),
    ("is eyeqdotnet.com working",
     '{"intent":"net.checkurl","args":{"url":"https://eyeqdotnet.com"},"trigger":"check url https://eyeqdotnet.com"}'),
    ("read files from /home/user/downloads",
     '{"intent":"fs.list","args":{"path":"/home/user/downloads"},"trigger":"list /home/user/downloads"}'),
    ("explain how docker works",
     '{"intent":"llm.chat","args":{},"trigger":""}'),
]


def _build_system_prompt() -> str:
    all_examples = list(_BUILTIN_EXAMPLES)
    for intent, phrase, args_dict, trigger_tpl in _DYNAMIC_EXAMPLES:
        try:
            trigger = trigger_tpl.format_map(args_dict) if trigger_tpl else intent
        except KeyError:
            trigger = trigger_tpl
        json_out = json.dumps({"intent": intent, "args": args_dict, "trigger": trigger})
        all_examples.append((phrase, json_out))

    schema_lines  = [f"  {k}: {json.dumps(v)}" for k, v in INTENT_SCHEMA.items()]
    trigger_lines = [f"  {k}: \"{v}\"" for k, v in TRIGGER_MAP.items()]
    shot_lines    = [f'User: "{u}"\nOutput: {o}' for u, o in all_examples]

    return (
        "You are the input processor for Jarvis, a modular AI OS assistant.\n"
        "Your ONLY job: convert the user's natural language into a structured JSON command.\n"
        "\n"
        "Return EXACTLY one JSON object on one line -- no markdown, no explanation:\n"
        '  {"intent": "<id>", "args": {...}, "trigger": "<canonical phrase>"}\n'
        "\n"
        "=== RULES ===\n"
        "1. intent  -- pick the single best match from the schema below.\n"
        "2. args    -- extract typed values from the user's words. Omit optional args if not mentioned.\n"
        "3. trigger -- the canonical phrase for this intent (see TRIGGER MAP). Fill {placeholders} from args.\n"
        "4. Time    -- convert to delay_seconds: minutes*60, hours*3600, days*86400.\n"
        "5. Strip filler words (please, can you, could you, etc.) from titles/messages.\n"
        "6. If the user is asking a general question with no clear OS action, use llm.chat.\n"
        "7. NEVER return anything except the JSON object. No prose. No explanation.\n"
        "\n"
        "=== INTENT SCHEMA ===\n" + "\n".join(schema_lines) + "\n\n"
        "=== TRIGGER MAP ===\n" + "\n".join(trigger_lines) + "\n\n"
        "=== EXAMPLES ===\n" + "\n\n".join(shot_lines)
    )


_CACHED_PROMPT: str | None = None


def _system_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is None:
        _CACHED_PROMPT = _build_system_prompt()
    return _CACHED_PROMPT


def invalidate_prompt_cache() -> None:
    global _CACHED_PROMPT
    _CACHED_PROMPT = None


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
def _llm_call(user_text: str, system_override: str | None = None) -> str:
    cfg = get_llm_config()
    payload = json.dumps({
        "model"      : cfg.get("model", ""),
        "messages"   : [
            {"role": "system", "content": system_override or _system_prompt()},
            {"role": "user",   "content": user_text},
        ],
        "max_tokens" : 200,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {cfg.get('api_key', '')}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Parsing + validation
# ---------------------------------------------------------------------------
def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        raise json.JSONDecodeError("No JSON object found", raw, 0)
    return json.loads(raw[s:e + 1])


def _coerce_args(intent: str, args: dict) -> dict:
    schema = INTENT_SCHEMA.get(intent, {})
    out = {}
    for arg, typ in schema.items():
        if arg not in args:
            continue
        base = typ.rstrip("?")
        val  = args[arg]
        try:
            if base == "int":     val = int(val)
            elif base == "float": val = float(val)
            else:                 val = str(val).strip()
        except (ValueError, TypeError):
            pass
        out[arg] = val
    for k, v in args.items():
        if k not in out:
            out[k] = v
    return out


def _build_trigger(intent: str, args: dict) -> str:
    template = TRIGGER_MAP.get(intent, "")
    if not template:
        return ""
    try:
        return template.format_map({k: v for k, v in args.items() if v is not None})
    except KeyError:
        return template


def _validate(result: dict, original_text: str) -> dict:
    intent = result.get("intent", "")
    args   = result.get("args", {})
    if not isinstance(args, dict):
        args = {}
    if intent not in INTENT_SCHEMA:
        return {"intent": "llm.chat", "args": {}, "trigger": original_text}
    args    = _coerce_args(intent, args)
    missing = [a for a in _REQUIRED.get(intent, []) if not args.get(a)]
    if missing:
        return {"intent": "llm.chat", "args": {}, "trigger": original_text, "_missing": missing}
    trigger = result.get("trigger") or _build_trigger(intent, args) or original_text
    return {"intent": intent, "args": args, "trigger": trigger}


# ---------------------------------------------------------------------------
# Public classify()
# ---------------------------------------------------------------------------
def classify(text: str) -> dict:
    # Step 1: try keyword pre-classifier first (no LLM needed)
    keyword_result = _keyword_classify(text)
    if keyword_result:
        _debug_log(text, "[keyword]", keyword_result)
        return keyword_result

    # Step 2: fall back to LLM
    last_raw = ""
    for attempt in range(2):
        try:
            raw = _llm_call(
                text if attempt == 0
                else f"Fix this invalid JSON and return only valid JSON: {last_raw}"
            )
            last_raw = raw
            parsed   = _parse(raw)
            result   = _validate(parsed, text)
            _debug_log(text, raw, result)
            return result
        except json.JSONDecodeError:
            if attempt == 0:
                continue
            break
        except urllib.error.URLError as exc:
            _debug_log(text, "", {"error": str(exc)})
            return {"intent": "llm.chat", "args": {}, "trigger": text, "_error": f"LLM unreachable: {exc}"}
        except Exception as exc:
            _debug_log(text, "", {"error": str(exc)})
            return {"intent": "llm.chat", "args": {}, "trigger": text, "_error": str(exc)}
    return {"intent": "llm.chat", "args": {}, "trigger": text, "_error": "json_parse_failed"}


def _debug_log(text: str, raw: str, result: dict) -> None:
    import os
    if not os.environ.get("JARVIS_DEBUG"):
        return
    print(f"[router] input   : {text!r}")
    if raw:
        print(f"[router] llm_raw : {raw!r}")
    print(f"[router] intent  : {result.get('intent')}")
    print(f"[router] args    : {result.get('args')}")
    print(f"[router] source  : {result.get('_source', 'llm')}")
    print(f"[router] trigger : {result.get('trigger')!r}")
