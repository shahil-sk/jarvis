"""Intent Router v2 — structured schema + few-shot examples + output validation."""

import json
import os
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
    # clipboard
    "clip.read"      : {},
    "clip.write"     : {"content": "str"},
    # notify
    "notify.send"    : {"message": "str"},
    # scheduler
    "scheduler.add"  : {"delay_seconds": "int", "message": "str", "repeat": "str?"},
    "scheduler.list" : {},
    "scheduler.cancel": {"id": "int"},
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
    "llm.chat"       : {},
}

_REQUIRED: dict[str, list] = {
    k: [a for a, t in v.items() if not t.endswith("?")]
    for k, v in INTENT_SCHEMA.items()
}

_EXAMPLES = [
    ("how much ram am i using",                        '{"intent":"system.stats","args":{}}'),
    ("run git status",                                 '{"intent":"system.shell","args":{"cmd":"git status"}}'),
    ("open vscode",                                    '{"intent":"system.open","args":{"target":"code"}}'),
    ("show me what's in ~/downloads",                  '{"intent":"fs.list","args":{"path":"~/downloads"}}'),
    ("find all python files",                          '{"intent":"fs.find","args":{"pattern":"*.py"}}'),
    ("rename old.txt to new.txt",                      '{"intent":"fs.move","args":{"src":"old.txt","dst":"new.txt"}}'),
    ("what processes are eating my cpu",               '{"intent":"process.list","args":{}}'),
    ("kill chrome",                                    '{"intent":"process.kill","args":{"target":"chrome"}}'),
    ("is nginx running",                               '{"intent":"process.find","args":{"name":"nginx"}}'),
    ("ping google.com",                                '{"intent":"net.ping","args":{"host":"google.com"}}'),
    ("is github down",                                 '{"intent":"net.checkurl","args":{"url":"https://github.com"}}'),
    ("what's my public ip",                            '{"intent":"net.myip","args":{}}'),
    ("check my internet speed",                        '{"intent":"net.speedtest","args":{}}'),
    ("what's in my clipboard",                         '{"intent":"clip.read","args":{}}'),
    ("remind me in 10 minutes to call John",           '{"intent":"scheduler.add","args":{"delay_seconds":600,"message":"call John","repeat":""}}'),
    ("remind me to clean my godown drive in 2 hours",  '{"intent":"scheduler.add","args":{"delay_seconds":7200,"message":"clean godown drive","repeat":""}}'),
    ("remind me every day to drink water",             '{"intent":"scheduler.add","args":{"delay_seconds":86400,"message":"drink water","repeat":"daily"}}'),
    ("show my reminders",                              '{"intent":"scheduler.list","args":{}}'),
    ("remember this: fix the auth bug #work",          '{"intent":"notes.save","args":{"content":"fix the auth bug","tag":"work"}}'),
    ("search notes for docker",                        '{"intent":"notes.search","args":{"query":"docker"}}'),
    ("open my dev workspace",                          '{"intent":"launcher.workspace","args":{"name":"dev"}}'),
    # github examples
    ("show my repos",                                  '{"intent":"gh.list_repos","args":{}}'),
    ("show repo jarvis",                               '{"intent":"gh.get_repo","args":{"repo":"jarvis"}}'),
    ("list open issues in jarvis",                     '{"intent":"gh.list_issues","args":{"repo":"jarvis","state":"open"}}'),
    ("create issue in jarvis: login page crashes",     '{"intent":"gh.create_issue","args":{"repo":"jarvis","title":"login page crashes","body":""}}'),
    ("close issue 5 in jarvis",                        '{"intent":"gh.close_issue","args":{"repo":"jarvis","number":5}}'),
    ("show open PRs in jarvis",                        '{"intent":"gh.list_prs","args":{"repo":"jarvis","state":"open"}}'),
    ("latest commits on jarvis",                       '{"intent":"gh.list_commits","args":{"repo":"jarvis","branch":"","limit":10}}'),
    ("branches in jarvis",                             '{"intent":"gh.list_branches","args":{"repo":"jarvis"}}'),
    ("search github for fast python sqlite orm",       '{"intent":"gh.search_repos","args":{"query":"fast python sqlite orm"}}'),
    ("explain how docker networking works",            '{"intent":"llm.chat","args":{}}'),
]


def _build_system_prompt() -> str:
    schema_lines = [f"  {k}: {json.dumps(v)}" for k, v in INTENT_SCHEMA.items()]
    shot_lines   = [f'User: "{u}"\nOutput: {o}' for u, o in _EXAMPLES[-14:]]
    return (
        "You are an intent classifier for an AI OS assistant called Jarvis.\n"
        "Return ONLY a JSON object: {\"intent\": \"<id>\", \"args\": {...}}\n"
        "No markdown. No explanation. One line.\n\n"
        "Rules:\n"
        "- Pick the single best intent from the schema.\n"
        "- Extract ALL required args precisely from the user message.\n"
        "- Time: convert to delay_seconds (min*60, hr*3600, day*86400).\n"
        "- Strip filler (remind me to / please / can you).\n"
        "- state defaults: issues=open, prs=open.\n"
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
        if typ.rstrip("?") == "int" and arg in args:
            try:
                args[arg] = int(args[arg])
            except (ValueError, TypeError):
                pass
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
