"""Nmap plugin — network scanning via nmap CLI.

This plugin is fully self-describing via PluginCapability.
No changes to dispatcher.py or intent_router.py needed when adding
new scan modes -- just add a PluginCapability and a _SCAN_MODES entry.
"""

import re
import shutil
import subprocess
from plugins.base import PluginBase, PluginCapability


# ---------------------------------------------------------------------------
# Scan mode definitions -- single source of truth
# Adding a new mode: add one entry here and one PluginCapability below.
# ---------------------------------------------------------------------------
_SCAN_MODES: dict[str, tuple[str, bool]] = {
    "nmap.scan_normal"  : ("-T4 --open",          False),
    "nmap.scan_silent"  : ("-sS -T2 --open",       True),
    "nmap.scan_full"    : ("-p- -T4 --open",        False),
    "nmap.scan_version" : ("-sV -T4 --open",        False),
    "nmap.scan_os"      : ("-O -T4",                True),
    "nmap.scan_vuln"    : ("--script vuln -T4",     False),
    "nmap.scan_quick"   : ("-F -T4 --open",         False),
}

_KEYWORD_MODES: list[tuple[list[str], str]] = [
    (["silent", "stealth", "quiet"],              "nmap.scan_silent"),
    (["full", "all ports", "complete", "deep"],   "nmap.scan_full"),
    (["version", "service", "banner"],             "nmap.scan_version"),
    (["os", "operating system"],                   "nmap.scan_os"),
    (["vuln", "vulnerability", "cve"],             "nmap.scan_vuln"),
    (["quick", "fast", "rapid"],                   "nmap.scan_quick"),
]

_SCAN_KEYWORDS = [
    "nmap", "scan", "port scan", "portscan",
    "scan ports", "enumerate", "check ports",
    "vulnerability scan", "os detection", "service detection",
]


class Plugin(PluginBase):
    priority = 30

    capabilities = [
        PluginCapability(
            intent="nmap.scan_normal",
            description="Standard nmap port scan on a host (top 1000 ports)",
            args={"target": "str"},
            trigger_template="nmap scan {target}",
            examples=[
                ("scan example.com",         {"target": "example.com"}),
                ("nmap example.com",          {"target": "example.com"}),
                ("check open ports on 10.0.0.1", {"target": "10.0.0.1"}),
            ],
        ),
        PluginCapability(
            intent="nmap.scan_silent",
            description="Stealth SYN scan (requires root)",
            args={"target": "str"},
            trigger_template="nmap stealth scan {target}",
            examples=[
                ("do a stealth scan on 192.168.1.1", {"target": "192.168.1.1"}),
                ("silent nmap on example.com",        {"target": "example.com"}),
            ],
        ),
        PluginCapability(
            intent="nmap.scan_full",
            description="Full scan of all 65535 ports on a host",
            args={"target": "str"},
            trigger_template="nmap full scan {target}",
            examples=[
                ("scan all ports on scanme.nmap.org", {"target": "scanme.nmap.org"}),
                ("deep scan example.com",              {"target": "example.com"}),
            ],
        ),
        PluginCapability(
            intent="nmap.scan_version",
            description="Detect service versions running on open ports",
            args={"target": "str"},
            trigger_template="nmap version scan {target}",
            examples=[
                ("get service versions on example.com", {"target": "example.com"}),
                ("what services are running on 10.0.0.1", {"target": "10.0.0.1"}),
            ],
        ),
        PluginCapability(
            intent="nmap.scan_os",
            description="Detect the operating system of a host (requires root)",
            args={"target": "str"},
            trigger_template="nmap os scan {target}",
            examples=[
                ("detect os of 192.168.1.1", {"target": "192.168.1.1"}),
            ],
        ),
        PluginCapability(
            intent="nmap.scan_vuln",
            description="Run nmap vulnerability scripts on a host",
            args={"target": "str"},
            trigger_template="nmap vuln scan {target}",
            examples=[
                ("vulnerability scan on 10.0.0.1",  {"target": "10.0.0.1"}),
                ("check for CVEs on example.com",    {"target": "example.com"}),
            ],
        ),
        PluginCapability(
            intent="nmap.scan_quick",
            description="Quick scan of top 100 ports on a host",
            args={"target": "str"},
            trigger_template="nmap quick scan {target}",
            examples=[
                ("quick scan example.com", {"target": "example.com"}),
                ("fast nmap on 10.0.0.1",  {"target": "10.0.0.1"}),
            ],
        ),
    ]

    # keyword-fallback entry point
    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in _SCAN_KEYWORDS)

    def run(self, text: str, memory) -> str:
        target = _extract_target(text)
        if not target:
            return "Please specify a target. Example: scan example.com"
        mode = _detect_mode(text)
        return self.run_intent(mode, {"target": target})

    # LLM-routed entry point (called by dispatcher with typed args)
    def run_intent(self, intent: str, args: dict) -> str:
        target = args.get("target", "") if isinstance(args, dict) else str(args)
        if not target:
            return "No target specified for nmap scan."
        flags, needs_root = _SCAN_MODES.get(intent, _SCAN_MODES["nmap.scan_normal"])
        if needs_root:
            import os
            if os.geteuid() != 0:
                return (
                    f"The '{intent}' mode requires root privileges.\n"
                    "Run Jarvis with sudo or choose a non-privileged scan mode."
                )
        return _run_nmap(flags, target)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nmap_available() -> bool:
    return shutil.which("nmap") is not None


def _run_nmap(flags: str, target: str) -> str:
    if not _nmap_available():
        return "nmap is not installed. Run: sudo apt install nmap"
    cmd = ["nmap"] + flags.split() + [target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = (result.stdout + result.stderr).strip()
        return output if output else "nmap returned no output."
    except subprocess.TimeoutExpired:
        return f"nmap scan timed out after 120s for: {target}"
    except Exception as exc:
        return f"nmap execution failed: {exc}"


def _extract_target(text: str) -> str:
    ip = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", text)
    if ip:
        return ip.group(1)
    domain = re.search(
        r"\b([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+)\b", text
    )
    if domain:
        return domain.group(1)
    for kw in ["scan", "nmap", "check", "enumerate"]:
        m = re.search(rf"{kw}\s+(\S+)", text, re.IGNORECASE)
        if m:
            word = m.group(1).strip(".,;:")
            if word and word not in {"ports", "the", "my", "all"}:
                return word
    return ""


def _detect_mode(text: str) -> str:
    t = text.lower()
    for keywords, mode in _KEYWORD_MODES:
        if any(kw in t for kw in keywords):
            return mode
    return "nmap.scan_normal"
