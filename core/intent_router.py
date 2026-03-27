"""Intent Router v2 — structured schema + few-shot examples + output validation."""

import json
import urllib.request
import urllib.error
from core.config import get_llm_config

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
    # scheduler v2
    "scheduler.add"       : {"delay_seconds": "int?", "message": "str", "repeat": "str?", "fire_at": "float?"},
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
    "notes.save"     : {"content": "str", "tag": "str?"},
    "notes.list"     : {"tag": "str?"},
    "notes.search"   : {"query": "str"},
    "notes.delete"   : {"id": "int"},
    "notes.history"  : {},
    "notes.forget"   : {},
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
    # fallback
    "llm.chat"          : {},
}

_REQUIRED: dict[str, list] = {
    k: [a for a, t in v.items() if not t.endswith("?")]
    for k, v in INTENT_SCHEMA.items()
}

_PRI_MAP = {"low": 1, "medium": 2, "med": 2, "high": 3, "urgent": 4, "critical": 4}

_EXAMPLES = [
    # system
    ("how much ram am i using",                         '{"intent":"system.stats","args":{}}'),
    ("run git status",                                  '{"intent":"system.shell","args":{"cmd":"git status"}}'),
    ("kill chrome",                                     '{"intent":"process.kill","args":{"target":"chrome"}}'),
    ("is github down",                                  '{"intent":"net.checkurl","args":{"url":"https://github.com"}}'),
    ("summarize https://news.ycombinator.com",          '{"intent":"web.summarize","args":{"url":"https://news.ycombinator.com","focus":""}}'),
    ("latest news on AI",                               '{"intent":"web.news","args":{"topic":"AI"}}'),
    # scheduler
    ("remind me in 10 minutes to call John",            '{"intent":"scheduler.add","args":{"delay_seconds":600,"message":"call John","repeat":""}}'),
    ("remind me to clean my godown drive in 2 hours",   '{"intent":"scheduler.add","args":{"delay_seconds":7200,"message":"clean godown drive","repeat":""}}'),
    ("remind me at 3pm to review PR",                   '{"intent":"scheduler.add_at","args":{"time_str":"3pm","message":"review PR","repeat":""}}'),
    ("remind me every day to drink water",              '{"intent":"scheduler.add","args":{"delay_seconds":86400,"message":"drink water","repeat":"daily"}}'),
    ("snooze reminder 3 for 10 minutes",                '{"intent":"scheduler.snooze","args":{"id":3,"delay_seconds":600}}'),
    ("reschedule reminder 2 to 5pm",                    '{"intent":"scheduler.reschedule","args":{"id":2,"time_str":"5pm"}}'),
    ("show my reminders",                               '{"intent":"scheduler.list","args":{}}'),
    ("cancel reminder 3",                               '{"intent":"scheduler.cancel","args":{"id":3}}'),
    # todo
    ("add todo fix the login bug",                      '{"intent":"todo.add","args":{"title":"fix the login bug","priority":"medium"}}'),
    ("add task write tests for auth !high #backend @jarvis due tomorrow", '{"intent":"todo.add","args":{"title":"write tests for auth","priority":"high","tags":"backend","project":"jarvis","due":"tomorrow"}}'),
    ("show my todos",                                   '{"intent":"todo.list","args":{}}'),
    ("show all done todos",                             '{"intent":"todo.list","args":{"status":"done"}}'),
    ("todos tagged backend",                            '{"intent":"todo.list","args":{"tag":"backend"}}'),
    ("mark todo 4 as done",                             '{"intent":"todo.complete","args":{"id":4}}'),
    ("start working on todo 2",                         '{"intent":"todo.start","args":{"id":2}}'),
    ("todo 5 is blocked",                               '{"intent":"todo.block","args":{"id":5}}'),
    ("delete todo 3",                                   '{"intent":"todo.delete","args":{"id":3}}'),
    ("search todos for docker",                         '{"intent":"todo.search","args":{"query":"docker"}}'),
    ("what's due today",                                '{"intent":"todo.due","args":{}}'),
    ("todo stats",                                      '{"intent":"todo.stats","args":{}}'),
    # notes / github / launcher
    ("remember this: fix auth bug #work",               '{"intent":"notes.save","args":{"content":"fix auth bug","tag":"work"}}'),
    ("open my dev workspace",                           '{"intent":"launcher.workspace","args":{"name":"dev"}}'),
    ("show my repos",                                   '{"intent":"gh.list_repos","args":{}}'),
    ("list open issues in jarvis",                      '{"intent":"gh.list_issues","args":{"repo":"jarvis","state":"open"}}'),
    ("explain how docker works",                        '{"intent":"llm.chat","args":{}}'),
]


def _build_system_prompt() -> str:
    schema_lines = [f"  {k}: {json.dumps(v)}" for k, v in INTENT_SCHEMA.items()]
    shot_lines   = [f'User: "{u}"\nOutput: {o}' for u, o in _EXAMPLES[-18:]]
    return (
        "You are an intent classifier for an AI OS assistant called Jarvis.\n"
        "Return ONLY a JSON object: {\"intent\": \"<id>\", \"args\": {...}}\n"
        "No markdown. No explanation. One line.\n\n"
        "Rules:\n"
        "- Pick the single best intent from the schema.\n"
        "- Time: convert to delay_seconds (min*60, hr*3600, day*86400).\n"
        "- For 'at <time>' reminders use scheduler.add_at with time_str.\n"
        "- Todo priority words: low=1, medium=2, high=3, urgent=4.\n"
        "- Strip filler words from titles/messages.\n"
        "- state defaults: issues=open, prs=open, todos=active.\n"
        "- If nothing fits, use llm.chat.\n\n"
        "Schema:\n" + "\n".join(schema_lines) + "\n\n"
        "Examples:\n" + "\n\n".join(shot_lines)
    )


_CACHED_PROMPT: str | None = None


def _system_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is None:
        _CACHED_PROMPT = _build_system_prompt()
    return _CACHED_PROMPT


def _llm_call(user_text: str) -> str:
    cfg = get_llm_config()
    payload = json.dumps({
        "model"      : cfg.get("model", ""),
        "messages"   : [
            {"role": "system", "content": _system_prompt()},
            {"role": "user",   "content": user_text},
        ],
        "max_tokens" : 120,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {cfg.get('api_key','')}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e != -1:
        raw = raw[s:e+1]
    return json.loads(raw)


def _validate(result: dict) -> dict:
    intent = result.get("intent", "")
    args   = result.get("args", {})
    if intent not in INTENT_SCHEMA:
        return {"intent": "llm.chat", "args": {}}
    for arg, typ in INTENT_SCHEMA[intent].items():
        base = typ.rstrip("?")
        if arg in args:
            if base == "int":
                try: args[arg] = int(args[arg])
                except: pass
            elif base == "float":
                try: args[arg] = float(args[arg])
                except: pass
    for arg in _REQUIRED.get(intent, []):
        if arg not in args or args[arg] == "" or args[arg] is None:
            return {"intent": "llm.chat", "args": {}, "_missing": arg}
    return {"intent": intent, "args": args}


def classify(text: str) -> dict:
    for attempt in range(2):
        try:
            return _validate(_parse(_llm_call(text)))
        except json.JSONDecodeError:
            if attempt == 0:
                continue
            return {"intent": "llm.chat", "args": {}, "_error": "json_decode"}
        except Exception as e:
            return {"intent": "llm.chat", "args": {}, "_error": str(e)}
    return {"intent": "llm.chat", "args": {}}
