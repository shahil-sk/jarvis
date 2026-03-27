"""Intent Router — asks LLM to classify input into a structured intent+args dict.

Replaces keyword matching. Every plugin registers its intents here.
The LLM returns JSON: {"intent": "plugin.action", "args": {...}}
"""

import json
import urllib.request
import urllib.error
from core.config import get_llm_config

# ── Intent registry ────────────────────────────────────────────────────────
# Each entry: "plugin.action": "plain english description of when to use + args"

INTENT_REGISTRY = {
    # system
    "system.stats"    : "User wants CPU, RAM, disk, or memory usage stats. args: {}",
    "system.uptime"   : "User asks how long Jarvis has been running. args: {}",
    "system.sysinfo"  : "User asks about OS, platform, Python version, machine info. args: {}",
    "system.shell"    : "User wants to run a terminal/shell command. args: {\"cmd\": \"<command string>\"}",
    "system.open"     : "User wants to open an application or file by name. args: {\"target\": \"<app or path>\"}",
    "system.env"      : "User wants to read an environment variable. args: {\"key\": \"<VAR_NAME or empty for all>\"}",
    "system.setenv"   : "User wants to set an environment variable. args: {\"key\": \"KEY\", \"value\": \"VALUE\"}",

    # filesystem
    "fs.find"         : "User wants to find or search for a file by name or pattern. args: {\"pattern\": \"<glob>\"}",
    "fs.read"         : "User wants to read or view contents of a file. args: {\"path\": \"<path>\"}",
    "fs.list"         : "User wants to list files in a directory. args: {\"path\": \"<dir path or .>\"}",
    "fs.move"         : "User wants to move or rename a file. args: {\"src\": \"<source>\", \"dst\": \"<destination>\"}",
    "fs.delete"       : "User wants to delete a file. args: {\"path\": \"<path>\"}",
    "fs.mkdir"        : "User wants to create a directory. args: {\"path\": \"<path>\"}",
    "fs.pwd"          : "User wants to know the current working directory. args: {}",

    # process
    "process.list"    : "User wants to see running processes. args: {}",
    "process.kill"    : "User wants to kill or stop a process by name or PID. args: {\"target\": \"<name or pid>\"}",
    "process.find"    : "User wants to find a specific running process. args: {\"name\": \"<process name>\"}",

    # network
    "net.ping"        : "User wants to ping a host. args: {\"host\": \"<hostname or ip>\"}",
    "net.curl"        : "User wants to fetch a URL or make an HTTP GET request. args: {\"url\": \"<url>\"}",
    "net.download"    : "User wants to download a file from a URL. args: {\"url\": \"<url>\"}",
    "net.portscan"    : "User wants to scan ports on a host. args: {\"host\": \"<hostname or ip>\"}",
    "net.myip"        : "User wants to know their public IP address. args: {}",
    "net.ipinfo"      : "User wants info about an IP address. args: {\"ip\": \"<ip or domain>\"}",
    "net.dns"         : "User wants to resolve a hostname via DNS. args: {\"host\": \"<hostname>\"}",
    "net.checkurl"    : "User wants to check if a website or URL is up. args: {\"url\": \"<url>\"}",
    "net.localip"     : "User wants their local IP or hostname. args: {}",
    "net.speedtest"   : "User wants to test their internet download speed. args: {}",

    # clipboard
    "clip.read"       : "User wants to read or see what is in the clipboard. args: {}",
    "clip.write"      : "User wants to copy something to the clipboard. args: {\"content\": \"<text>\"}",

    # notify
    "notify.send"     : "User wants to send a desktop notification or alert. args: {\"message\": \"<text>\"}",

    # scheduler
    "scheduler.add"   : "User wants to set a reminder or schedule something. args: {\"delay_seconds\": <int>, \"message\": \"<text>\", \"repeat\": \"\" or \"minutely\" or \"hourly\" or \"daily\"}",
    "scheduler.list"  : "User wants to see pending reminders. args: {}",
    "scheduler.cancel": "User wants to cancel a reminder by ID. args: {\"id\": <int>}",

    # notes
    "notes.save"      : "User wants to save a note or remember something. args: {\"content\": \"<text>\", \"tag\": \"<optional tag>\"}",
    "notes.list"      : "User wants to see their notes. args: {\"tag\": \"<optional tag>\"}",
    "notes.search"    : "User wants to search their notes. args: {\"query\": \"<search term>\"}",
    "notes.delete"    : "User wants to delete a note by ID. args: {\"id\": <int>}",
    "notes.history"   : "User wants to see conversation history. args: {}",
    "notes.forget"    : "User wants to wipe all memory/history. args: {}",

    # launcher
    "launcher.workspace" : "User wants to open/launch a named workspace. args: {\"name\": \"<workspace name>\"}",
    "launcher.list"      : "User wants to list available workspaces. args: {}",

    # llm (fallback)
    "llm.chat"        : "None of the above apply. User wants a general answer or conversation. args: {}",
}


_SYSTEM_PROMPT = """You are an intent classifier for an AI assistant called Jarvis.
Given the user's message, return ONLY a JSON object with:
  {"intent": "<intent_id>", "args": {<extracted args>}}

Available intents:
"""


def build_classifier_prompt() -> str:
    lines = []
    for intent, desc in INTENT_REGISTRY.items():
        lines.append(f"  {intent}: {desc}")
    return _SYSTEM_PROMPT + "\n".join(lines) + """

Rules:
- Return ONLY valid JSON. No explanation, no markdown.
- Pick the single best matching intent.
- Extract args precisely from the user message.
- If delay is mentioned (e.g. '10 minutes'), convert to seconds in delay_seconds.
- Default to llm.chat if nothing matches."""


def classify(text: str) -> dict:
    """
    Send text to LLM for intent classification.
    Returns {"intent": str, "args": dict} or fallback to llm.chat.
    """
    cfg = get_llm_config()
    base_url = cfg.get("base_url", "").rstrip("/")
    api_key  = cfg.get("api_key", "")
    model    = cfg.get("model", "")

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": build_classifier_prompt()},
            {"role": "user",   "content": text},
        ],
        "max_tokens": 150,
        "temperature": 0.0,  # deterministic for classification
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data  = json.loads(resp.read())
            raw   = data["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if model wraps in ```json
            raw   = raw.strip("`").lstrip("json").strip()
            result = json.loads(raw)
            if "intent" not in result:
                raise ValueError("missing intent")
            return result
    except Exception as e:
        return {"intent": "llm.chat", "args": {}, "_error": str(e)}
