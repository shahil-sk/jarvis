"""Intent Router v3 — LLM-first pipeline.

Flow
----
Every user input goes to the LLM first (no fast-rule shortcuts that silently
skip intent classification). The LLM returns a structured JSON with:

  {
    "intent": "<namespace.action>",   # one of INTENT_SCHEMA keys
    "args":   { ... },                # typed args for the plugin
    "trigger": "<canonical phrase>"   # the exact phrase the plugin's
                                       # matches() function will recognise
                                       # (used when --no-llm-routing is on)
  }

The `trigger` field is the key addition: even in keyword-fallback mode the
dispatcher now uses the LLM-normalised trigger instead of the raw user input,
so plugins always receive something they can reliably match.

Retry logic
-----------
- Attempt 1: strict JSON parse + schema validation.
- Attempt 2: same, but we also ask the LLM to fix the bad JSON it returned.
- Final fallback: {"intent": "llm.chat", "args": {}, "trigger": <text>}
"""

import json
import urllib.request
import urllib.error
from core.config import get_llm_config

# ---------------------------------------------------------------------------
# Intent schema — single source of truth for every plugin intent + its args
# ---------------------------------------------------------------------------
INTENT_SCHEMA: dict[str, dict] = {
    # system
    "system.stats"   : {},
    "system.uptime"  : {},
    "system.sysinfo" : {},
    "system.shell"   : {"cmd": "str"},
    "system.open"    : {"target": "str"},
    "system.env"     : {"key": "str?"},
    "system.setenv"  : {"key": "str", "value": "str"},
    # filesystem
    "fs.find"        : {"pattern": "str"},
    "fs.read"        : {"path": "str"},
    "fs.list"        : {"path": "str?"},
    "fs.move"        : {"src": "str", "dst": "str"},
    "fs.delete"      : {"path": "str"},
    "fs.mkdir"       : {"path": "str"},
    "fs.pwd"         : {},
    # process
    "process.list"   : {},
    "process.kill"   : {"target": "str"},
    "process.find"   : {"name": "str"},
    # network
    "net.ping"       : {"host": "str"},
    "net.curl"       : {"url": "str"},
    "net.download"   : {"url": "str"},
    "net.portscan"   : {"host": "str"},
    "net.myip"       : {},
    "net.ipinfo"     : {"ip": "str"},
    "net.dns"        : {"host": "str"},
    "net.checkurl"   : {"url": "str"},
    "net.localip"    : {},
    "net.speedtest"  : {},
    # web
    "web.summarize"  : {"url": "str", "focus": "str?"},
    "web.read"       : {"url": "str"},
    "web.ask"        : {"url": "str", "question": "str"},
    "web.extract"    : {"url": "str", "what": "str"},
    "web.compare"    : {"url1": "str", "url2": "str", "aspect": "str?"},
    "web.search"     : {"query": "str"},
    "web.news"       : {"topic": "str"},
    # clipboard
    "clip.read"      : {},
    "clip.write"     : {"content": "str"},
    # notify
    "notify.send"    : {"message": "str"},
    # scheduler
    "scheduler.add"       : {"delay_seconds": "int?", "message": "str", "repeat": "str?"},
    "scheduler.add_at"    : {"time_str": "str", "message": "str", "repeat": "str?"},
    "scheduler.list"      : {},
    "scheduler.cancel"    : {"id": "int"},
    "scheduler.snooze"    : {"id": "int", "delay_seconds": "int?"},
    "scheduler.reschedule": {"id": "int", "time_str": "str"},
    # todo
    "todo.add"      : {"title": "str", "priority": "str?", "tags": "str?", "due": "str?", "project": "str?"},
    "todo.list"     : {"status": "str?", "tag": "str?", "project": "str?"},
    "todo.complete" : {"id": "int"},
    "todo.start"    : {"id": "int"},
    "todo.block"    : {"id": "int"},
    "todo.reopen"   : {"id": "int"},
    "todo.delete"   : {"id": "int"},
    "todo.edit"     : {"id": "int", "title": "str?", "priority": "str?", "due": "str?", "tags": "str?", "project": "str?"},
    "todo.search"   : {"query": "str"},
    "todo.due"      : {},
    "todo.stats"    : {},
    # notes
    "notes.save"    : {"content": "str", "tag": "str?"},
    "notes.list"    : {"tag": "str?"},
    "notes.search"  : {"query": "str"},
    "notes.delete"  : {"id": "int"},
    "notes.history" : {},
    "notes.forget"  : {},
    # launcher
    "launcher.workspace": {"name": "str"},
    "launcher.list"     : {},
    # github
    "gh.list_repos"     : {"limit": "int?"},
    "gh.get_repo"       : {"repo": "str"},
    "gh.list_issues"    : {"repo": "str", "state": "str?"},
    "gh.create_issue"   : {"repo": "str", "title": "str", "body": "str?"},
    "gh.close_issue"    : {"repo": "str", "number": "int"},
    "gh.list_prs"       : {"repo": "str", "state": "str?"},
    "gh.list_commits"   : {"repo": "str", "branch": "str?", "limit": "int?"},
    "gh.list_branches"  : {"repo": "str"},
    "gh.search_repos"   : {"query": "str"},
    # brightness
    "brightness.get"    : {},
    "brightness.set"    : {"level": "int"},
    "brightness.up"     : {},
    "brightness.down"   : {},
    # stopwatch
    "stopwatch.start"   : {"name": "str?"},
    "stopwatch.stop"    : {"name": "str?"},
    "stopwatch.pause"   : {"name": "str?"},
    "stopwatch.resume"  : {"name": "str?"},
    "stopwatch.lap"     : {"name": "str?"},
    "stopwatch.elapsed" : {"name": "str?"},
    "stopwatch.list"    : {},
    "stopwatch.reset"   : {"name": "str?"},
    # env
    "env.get"    : {"key": "str"},
    "env.set"    : {"key": "str", "value": "str"},
    "env.unset"  : {"key": "str"},
    "env.list"   : {},
    "env.search" : {"keyword": "str"},
    # clipboard history
    "clip_history.list"   : {"limit": "int?"},
    "clip_history.search" : {"keyword": "str"},
    "clip_history.recopy" : {"index": "int"},
    "clip_history.clear"  : {},
    # nmap
    "nmap.scan_normal"  : {"target": "str"},
    "nmap.scan_silent"  : {"target": "str"},
    "nmap.scan_full"    : {"target": "str"},
    "nmap.scan_version" : {"target": "str"},
    "nmap.scan_os"      : {"target": "str"},
    "nmap.scan_vuln"    : {"target": "str"},
    "nmap.scan_quick"   : {"target": "str"},
    # llm fallback
    "llm.chat"          : {},
}

# ---------------------------------------------------------------------------
# Canonical trigger phrases
# ---------------------------------------------------------------------------
TRIGGER_MAP: dict[str, str] = {
    "system.stats"        : "system stats",
    "system.uptime"       : "system uptime",
    "system.sysinfo"      : "system info",
    "system.shell"        : "run {cmd}",
    "system.open"         : "open {target}",
    "system.env"          : "env {key}",
    "system.setenv"       : "set env {key}={value}",
    "fs.find"             : "find {pattern}",
    "fs.read"             : "read {path}",
    "fs.list"             : "list {path}",
    "fs.move"             : "move {src} to {dst}",
    "fs.delete"           : "delete file {path}",
    "fs.mkdir"            : "mkdir {path}",
    "fs.pwd"              : "current directory",
    "process.list"        : "list processes",
    "process.kill"        : "kill {target}",
    "process.find"        : "find process {name}",
    "net.ping"            : "ping {host}",
    "net.myip"            : "my public ip",
    "net.localip"         : "my local ip",
    "net.speedtest"       : "speed test",
    "net.dns"             : "dns {host}",
    "net.checkurl"        : "check url {url}",
    "net.download"        : "download {url}",
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
    "nmap.scan_normal"    : "nmap scan {target}",
    "nmap.scan_silent"    : "nmap stealth scan {target}",
    "nmap.scan_full"      : "nmap full scan {target}",
    "nmap.scan_version"   : "nmap version scan {target}",
    "nmap.scan_os"        : "nmap os scan {target}",
    "nmap.scan_vuln"      : "nmap vuln scan {target}",
    "nmap.scan_quick"     : "nmap quick scan {target}",
    "llm.chat"            : "",
}

_REQUIRED: dict[str, list] = {
    k: [a for a, t in v.items() if not t.endswith("?")]
    for k, v in INTENT_SCHEMA.items()
}

# ---------------------------------------------------------------------------
# Few-shot examples  (user text -> JSON)
# ---------------------------------------------------------------------------
_EXAMPLES = [
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
    ("remind me at 3pm to review PR",
     '{"intent":"scheduler.add_at","args":{"time_str":"3pm","message":"review PR"},"trigger":"remind me at 3pm review PR"}'),
    ("add todo fix the login bug high priority",
     '{"intent":"todo.add","args":{"title":"fix the login bug","priority":"high"},"trigger":"add todo fix the login bug"}'),
    ("show my todos",
     '{"intent":"todo.list","args":{},"trigger":"list todos"}'),
    ("mark todo 4 done",
     '{"intent":"todo.complete","args":{"id":4},"trigger":"complete todo 4"}'),
    ("save note buy milk #personal",
     '{"intent":"notes.save","args":{"content":"buy milk","tag":"personal"},"trigger":"save note buy milk"}'),
    ("open my dev workspace",
     '{"intent":"launcher.workspace","args":{"name":"dev"},"trigger":"open workspace dev"}'),
    ("show my repos",
     '{"intent":"gh.list_repos","args":{},"trigger":"list repos"}'),
    ("list open issues in jarvis",
     '{"intent":"gh.list_issues","args":{"repo":"jarvis","state":"open"},"trigger":"list issues jarvis"}'),
    ("can you turn the screen brightness up a little",
     '{"intent":"brightness.up","args":{},"trigger":"brightness up"}'),
    ("set brightness to 60 percent",
     '{"intent":"brightness.set","args":{"level":60},"trigger":"brightness set 60"}'),
    ("start timing the build",
     '{"intent":"stopwatch.start","args":{"name":"build"},"trigger":"start stopwatch build"}'),
    ("what is the value of PATH",
     '{"intent":"env.get","args":{"key":"PATH"},"trigger":"env PATH"}'),
    ("show clipboard history",
     '{"intent":"clip_history.list","args":{},"trigger":"clipboard history"}'),
    ("scan example.com",
     '{"intent":"nmap.scan_normal","args":{"target":"example.com"},"trigger":"nmap scan example.com"}'),
    ("do a stealth scan on 192.168.1.1",
     '{"intent":"nmap.scan_silent","args":{"target":"192.168.1.1"},"trigger":"nmap stealth scan 192.168.1.1"}'),
    ("check all ports on scanme.nmap.org",
     '{"intent":"nmap.scan_full","args":{"target":"scanme.nmap.org"},"trigger":"nmap full scan scanme.nmap.org"}'),
    ("vulnerability scan on 10.0.0.1",
     '{"intent":"nmap.scan_vuln","args":{"target":"10.0.0.1"},"trigger":"nmap vuln scan 10.0.0.1"}'),
    ("get service versions on example.com",
     '{"intent":"nmap.scan_version","args":{"target":"example.com"},"trigger":"nmap version scan example.com"}'),
    ("explain how docker works",
     '{"intent":"llm.chat","args":{},"trigger":""}'),
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------
def _build_system_prompt() -> str:
    schema_lines  = [f"  {k}: {json.dumps(v)}" for k, v in INTENT_SCHEMA.items()]
    trigger_lines = [f"  {k}: \"{v}\"" for k, v in TRIGGER_MAP.items()]
    shot_lines    = [f'User: "{u}"\nOutput: {o}' for u, o in _EXAMPLES]
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
        "3. trigger -- the canonical phrase for this intent (see TRIGGER MAP below).\n"
        "             Fill in {placeholders} from args. Use empty string for llm.chat.\n"
        "4. Time    -- convert to delay_seconds: minutes*60, hours*3600, days*86400.\n"
        "5. Priority words: low=1, medium=2, high=3, urgent=4.\n"
        "6. Strip filler words (please, can you, could you, I want to, etc.) from titles/messages.\n"
        "7. If the user is asking a question or having a conversation with no clear OS action, use llm.chat.\n"
        "8. For scan/nmap requests, extract the target host/IP and choose the right nmap.scan_* intent.\n"
        "9. NEVER return anything except the JSON object.\n"
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
    """Call this after dynamically registering new intents."""
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
    """Extract the first JSON object from LLM output (handles markdown fences)."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        raise json.JSONDecodeError("No JSON object found", raw, 0)
    return json.loads(raw[s:e + 1])


def _coerce_args(intent: str, args: dict) -> dict:
    """Coerce arg types per schema and return cleaned dict."""
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
    """Fill TRIGGER_MAP template with actual arg values."""
    template = TRIGGER_MAP.get(intent, "")
    if not template:
        return ""
    try:
        return template.format_map({k: v for k, v in args.items() if v is not None})
    except KeyError:
        return template


def _validate(result: dict, original_text: str) -> dict:
    """Validate schema, coerce types, fill trigger, enforce required args."""
    intent = result.get("intent", "")
    args   = result.get("args", {})
    if not isinstance(args, dict):
        args = {}

    if intent not in INTENT_SCHEMA:
        return {"intent": "llm.chat", "args": {}, "trigger": original_text}

    args = _coerce_args(intent, args)

    missing = [a for a in _REQUIRED.get(intent, []) if not args.get(a)]
    if missing:
        return {
            "intent"  : "llm.chat",
            "args"    : {},
            "trigger" : original_text,
            "_missing": missing,
        }

    trigger = result.get("trigger") or _build_trigger(intent, args) or original_text
    return {"intent": intent, "args": args, "trigger": trigger}


# ---------------------------------------------------------------------------
# Public classify() -- always returns a valid dict
# ---------------------------------------------------------------------------
def classify(text: str) -> dict:
    """
    Send user text to LLM and return:
      {"intent": str, "args": dict, "trigger": str}

    Never raises -- worst case returns llm.chat fallback.
    """
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
    """Print debug info when JARVIS_DEBUG=1."""
    import os
    if not os.environ.get("JARVIS_DEBUG"):
        return
    print(f"[router] input   : {text!r}")
    if raw:
        print(f"[router] llm_raw : {raw!r}")
    print(f"[router] intent  : {result.get('intent')}")
    print(f"[router] args    : {result.get('args')}")
    print(f"[router] trigger : {result.get('trigger')!r}")
    if "_missing" in result:
        print(f"[router] missing : {result['_missing']}")
    if "_error" in result:
        print(f"[router] error   : {result['_error']}")
