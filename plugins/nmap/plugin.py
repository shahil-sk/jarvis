"""Nmap plugin — network scanning via nmap CLI.

Intents handled
---------------
nmap.scan_normal  : standard port scan (top 1000 ports)
nmap.scan_silent  : stealth SYN scan (-sS), requires root
nmap.scan_full    : all 65535 ports (-p-)
nmap.scan_version : service/version detection (-sV)
nmap.scan_os      : OS detection (-O), requires root
nmap.scan_vuln    : vuln scripts (--script vuln)
nmap.scan_quick   : quick scan (-F top 100 ports)

All results are piped back to the LLM formatter for
human-readable output.
"""

import re
import shutil
import subprocess
from plugins.base import PluginBase


_SCAN_KEYWORDS = [
    "nmap", "scan", "port scan", "portscan",
    "scan ports", "enumerate", "check ports",
    "vulnerability scan", "os detection", "service detection",
]

_TRIGGER_MAP = {
    "nmap.scan_normal"  : ("-T4 --open",          False),
    "nmap.scan_silent"  : ("-sS -T2 --open",       True),
    "nmap.scan_full"    : ("-p- -T4 --open",        False),
    "nmap.scan_version" : ("-sV -T4 --open",        False),
    "nmap.scan_os"      : ("-O -T4",                True),
    "nmap.scan_vuln"    : ("--script vuln -T4",     False),
    "nmap.scan_quick"   : ("-F -T4 --open",         False),
}


def _nmap_available() -> bool:
    return shutil.which("nmap") is not None


def _run_nmap(flags: str, target: str) -> str:
    if not _nmap_available():
        return "nmap is not installed. Install it with: sudo apt install nmap"
    cmd = ["nmap"] + flags.split() + [target]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "nmap returned no output."
    except subprocess.TimeoutExpired:
        return f"nmap scan timed out after 120 seconds for target: {target}"
    except Exception as exc:
        return f"nmap execution failed: {exc}"


class Plugin(PluginBase):
    priority = 30

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in _SCAN_KEYWORDS)

    def run(self, text: str, memory) -> str:
        target = _extract_target(text)
        if not target:
            return "Please specify a target host or IP to scan. Example: scan example.com"

        mode = _extract_mode(text)
        flags, needs_root = _TRIGGER_MAP.get(mode, _TRIGGER_MAP["nmap.scan_normal"])

        if needs_root:
            import os
            if os.geteuid() != 0:
                return (
                    f"The '{mode}' scan requires root privileges.\n"
                    "Run Jarvis with sudo, or use a normal scan instead."
                )

        raw_output = _run_nmap(flags, target)
        return raw_output

    def run_intent(self, intent: str, target: str) -> str:
        """Direct intent-based entry point called by the dispatcher."""
        if not target:
            return "No target specified for nmap scan."
        flags, needs_root = _TRIGGER_MAP.get(intent, _TRIGGER_MAP["nmap.scan_normal"])

        if needs_root:
            import os
            if os.geteuid() != 0:
                return (
                    f"The '{intent}' scan mode requires root privileges.\n"
                    "Run Jarvis with sudo, or choose a non-privileged scan mode."
                )
        return _run_nmap(flags, target)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_target(text: str) -> str:
    """Pull a hostname or IP from the user's text."""
    # IPv4 pattern
    ip_match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", text)
    if ip_match:
        return ip_match.group(1)

    # Domain / hostname pattern
    domain_match = re.search(
        r"\b([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+)\b",
        text,
    )
    if domain_match:
        return domain_match.group(1)

    # Bare word after known keywords
    for kw in ["scan", "nmap", "ping", "check", "enumerate"]:
        m = re.search(rf"{kw}\s+(\S+)", text, re.IGNORECASE)
        if m:
            word = m.group(1).strip(".,;:")
            if word and word not in {"ports", "the", "my", "all"}:
                return word

    return ""


_MODE_KEYWORDS: list[tuple[list[str], str]] = [
    (["silent", "stealth", "quiet", "sneaky"],           "nmap.scan_silent"),
    (["full", "all ports", "complete", "deep"],           "nmap.scan_full"),
    (["version", "service", "banner"],                    "nmap.scan_version"),
    (["os", "operating system", "detect os"],             "nmap.scan_os"),
    (["vuln", "vulnerability", "cve", "exploit"],         "nmap.scan_vuln"),
    (["quick", "fast", "rapid"],                          "nmap.scan_quick"),
]


def _extract_mode(text: str) -> str:
    t = text.lower()
    for keywords, mode in _MODE_KEYWORDS:
        if any(kw in t for kw in keywords):
            return mode
    return "nmap.scan_normal"
