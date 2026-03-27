"""Intent Router v2 — structured schema + few-shot examples + output validation.

Improvements over v1:
  - Compact schema (name + args spec only, no verbose descriptions)
  - Few-shot examples baked into system prompt
  - Output validated + coerced before returning
  - Retries once on bad JSON
  - Shared LLM call helper to avoid code duplication
"""

import json
import urllib.request
import urllib.error
from core.config import get_llm_config

# ─────────────────────────────────────────────────────────────────────
# Intent schema: {intent_id: {arg_name: type_hint}}
# Empty dict = no args needed.
# ─────────────────────────────────────────────────────────────────────

INTENT_SCHEMA: dict[str, dict] = {
    # —— system ——
    "system.stats"   : {},
    "system.uptime"  : {},
    "system.sysinfo" : {},
    "system.shell"   : {"cmd": "str"},
    "system.open"    : {"target": "str"},
    "system.env"     : {"key": "str?"},        # optional
    "system.setenv"  : {"key": "str", "value": "str"},

    # —— filesystem ——
    "fs.find"        : {"pattern": "str"},
    "fs.read"        : {"path": "str"},
    "fs.list"        : {"path": "str?"},
    "fs.move"        : {"src": "str", "dst": "str"},
    "fs.delete"      : {"path": "str"},
    "fs.mkdir"       : {"path": "str"},
    "fs.pwd"         : {},

    # —— process ——
    "process.list"   : {},
    "process.kill"   : {"target": "str"},
    "process.find"   : {"name": "str"},

    # —— network ——
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

    # —— clipboard ——
    "clip.read"      : {},
    "clip.write"     : {"content": "str"},

    # —— notify ——
    "notify.send"    : {"message": "str"},

    # —— scheduler ——
    "scheduler.add"  : {"delay_seconds": "int", "message": "str", "repeat": "str?"},
    "scheduler.list" : {},
    "scheduler.cancel": {"id": "int"},

    # —— notes ——
    "notes.save"     : {"content": "str", "tag": "str?"},
    "notes.list"     : {"tag": "str?"},
    "notes.search"   : {"query": "str"},
    "notes.delete"   : {"id": "int"},
    "notes.history"  : {},
    "notes.forget"   : {},

    # —— launcher ——
    "launcher.workspace": {"name": "str"},
    "launcher.list"     : {},

    # —— fallback ——
    "llm.chat"       : {},
}

# Required args (non-optional) per intent for validation
_REQUIRED: dict[str, list] = {
    k: [a for a, t in v.items() if not t.endswith("?")]
    for k, v in INTENT_SCHEMA.items()
}

# ─────────────────────────────────────────────────────────────────────
# Few-shot examples — teach the model intent + arg extraction
# ─────────────────────────────────────────────────────────────────────

_EXAMPLES = [
    # system
    ("how much ram am i using",                   '{"intent":"system.stats","args":{}}'),
    ("run git status",                             '{"intent":"system.shell","args":{"cmd":"git status"}}'),
    ("open vscode",                                '{"intent":"system.open","args":{"target":"code"}}'),
    ("what os am i on",                            '{"intent":"system.sysinfo","args":{}}'),
    ("set HOME_DIR to /home/shahil",               '{"intent":"system.setenv","args":{"key":"HOME_DIR","value":"/home/shahil"}}'),

    # filesystem
    ("show me what's in ~/downloads",              '{"intent":"fs.list","args":{"path":"~/downloads"}}'),
    ("find all python files",                      '{"intent":"fs.find","args":{"pattern":"*.py"}}'),
    ("read the config file at ./config.yaml",      '{"intent":"fs.read","args":{"path":"./config.yaml"}}'),
    ("rename old.txt to new.txt",                  '{"intent":"fs.move","args":{"src":"old.txt","dst":"new.txt"}}'),
    ("create a folder called backups",             '{"intent":"fs.mkdir","args":{"path":"backups"}}'),
    ("where am i",                                 '{"intent":"fs.pwd","args":{}}'),

    # process
    ("what processes are eating my cpu",           '{"intent":"process.list","args":{}}'),
    ("kill chrome",                                '{"intent":"process.kill","args":{"target":"chrome"}}'),
    ("is nginx running",                           '{"intent":"process.find","args":{"name":"nginx"}}'),

    # network
    ("ping google.com",                            '{"intent":"net.ping","args":{"host":"google.com"}}'),
    ("is github down",                             '{"intent":"net.checkurl","args":{"url":"https://github.com"}}'),
    ("what's my public ip",                        '{"intent":"net.myip","args":{}}'),
    ("scan ports on 192.168.1.1",                  '{"intent":"net.portscan","args":{"host":"192.168.1.1"}}'),
    ("download https://example.com/file.zip",      '{"intent":"net.download","args":{"url":"https://example.com/file.zip"}}'),
    ("what city is 8.8.8.8 in",                    '{"intent":"net.ipinfo","args":{"ip":"8.8.8.8"}}'),
    ("check my internet speed",                    '{"intent":"net.speedtest","args":{}}'),

    # clipboard
    ("what's in my clipboard",                     '{"intent":"clip.read","args":{}}'),
    ("copy 'hello world' to clipboard",            '{"intent":"clip.write","args":{"content":"hello world"}}'),

    # notify
    ("send me a notification: build done",         '{"intent":"notify.send","args":{"message":"build done"}}'),

    # scheduler - time conversion examples
    ("remind me in 10 minutes to call John",       '{"intent":"scheduler.add","args":{"delay_seconds":600,"message":"call John","repeat":""}}'),
    ("remind me to clean my godown drive in 2 hours", '{"intent":"scheduler.add","args":{"delay_seconds":7200,"message":"clean godown drive","repeat":""}}'),
    ("remind me every day to drink water",         '{"intent":"scheduler.add","args":{"delay_seconds":86400,"message":"drink water","repeat":"daily"}}'),
    ("show my reminders",                          '{"intent":"scheduler.list","args":{}}'),
    ("cancel reminder 3",                          '{"intent":"scheduler.cancel","args":{"id":3}}'),

    # notes
    ("remember this: fix the auth bug #work",      '{"intent":"notes.save","args":{"content":"fix the auth bug","tag":"work"}}'),
    ("show all my notes",                          '{"intent":"notes.list","args":{}}'),
    ("search notes for docker",                    '{"intent":"notes.search","args":{"query":"docker"}}'),
    ("what did i say earlier",                     '{"intent":"notes.history","args":{}}'),

    # launcher
    ("open my dev workspace",                      '{"intent":"launcher.workspace","args":{"name":"dev"}}'),
    ("what workspaces do i have",                  '{"intent":"launcher.list","args":{}}'),

    # llm fallback
    ("explain how docker networking works",        '{"intent":"llm.chat","args":{}}'),
    ("what's the capital of japan",                '{"intent":"llm.chat","args":{}}'),
]


def _build_system_prompt() -> str:
    # Compact schema block
    schema_lines = []
    for intent, args in INTENT_SCHEMA.items():
        args_str = json.dumps(args) if args else "{}"
        schema_lines.append(f"  {intent}: {args_str}")
    schema_block = "\n".join(schema_lines)

    # Few-shot block (last 12 examples, rotated to keep prompt small)
    shot_lines = []
    for user, out in _EXAMPLES[-12:]:
        shot_lines.append(f'User: "{user}"\nOutput: {out}')
    shots = "\n\n".join(shot_lines)

    return f"""You are an intent classifier for an AI OS assistant called Jarvis.

Return ONLY a JSON object: {{"intent": "<id>", "args": {{...}}}}
No markdown. No explanation. One line.

Rules:
- Pick the single best intent from the schema below.
- Extract ALL required args precisely from the user message.
- For time: convert to delay_seconds (minutes*60, hours*3600, days*86400).
- Strip filler words from messages (remind me to / please / can you).
- If nothing fits, use llm.chat with empty args.

Schema:
{schema_block}

Examples:
{shots}"""


# Cache the prompt (built once per process)
_CACHED_PROMPT: str | None = None


def _system_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is None:
        _CACHED_PROMPT = _build_system_prompt()
    return _CACHED_PROMPT


# ─────────────────────────────────────────────────────────────────────
# LLM call + parse
# ─────────────────────────────────────────────────────────────────────

def _llm_call(user_text: str) -> str:
    """Raw LLM call. Returns the model's text output."""
    cfg = get_llm_config()
    payload = json.dumps({
        "model"      : cfg.get("model", ""),
        "messages"   : [
            {"role": "system", "content": _system_prompt()},
            {"role": "user",   "content": user_text},
        ],
        "max_tokens" : 120,     # intent JSON never needs more
        "temperature": 0.0,     # fully deterministic
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
    """Extract JSON from model output, strip markdown fences if present."""
    raw = raw.strip()
    # strip ```json ... ``` or ``` ... ```
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # find first { ... }
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end+1]
    return json.loads(raw)


def _validate(result: dict) -> dict:
    """Ensure intent exists in schema and required args are present.
    Coerces int args from strings. Falls back to llm.chat on failure.
    """
    intent = result.get("intent", "")
    args   = result.get("args", {})

    if intent not in INTENT_SCHEMA:
        return {"intent": "llm.chat", "args": {}}

    schema = INTENT_SCHEMA[intent]
    # Coerce types
    for arg, typ in schema.items():
        base_typ = typ.rstrip("?")
        if arg in args and base_typ == "int":
            try:
                args[arg] = int(args[arg])
            except (ValueError, TypeError):
                pass

    # Check required args present
    for arg in _REQUIRED.get(intent, []):
        if arg not in args or args[arg] == "" or args[arg] is None:
            # Missing required arg — fall back to LLM chat
            return {"intent": "llm.chat", "args": {}, "_missing": arg}

    return {"intent": intent, "args": args}


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def classify(text: str) -> dict:
    """
    Classify user text into {intent, args}.
    Retries once on bad JSON. Always returns a valid dict.
    """
    for attempt in range(2):
        try:
            raw    = _llm_call(text)
            result = _parse(raw)
            return _validate(result)
        except json.JSONDecodeError:
            if attempt == 0:
                continue   # retry once
            return {"intent": "llm.chat", "args": {}, "_error": "json_decode_failed"}
        except urllib.error.URLError as e:
            return {"intent": "llm.chat", "args": {}, "_error": str(e)}
        except Exception as e:
            return {"intent": "llm.chat", "args": {}, "_error": str(e)}
    return {"intent": "llm.chat", "args": {}}
