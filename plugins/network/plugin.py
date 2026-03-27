"""Network plugin — ping, curl/GET, download, port scan, IP info. stdlib only."""

import socket
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import platform
import os
import re
import time
from plugins.base import PluginBase

_INTENTS = {
    ("ping ",)                                              : "_ping",
    ("curl ", "get ", "fetch url", "http get")              : "_curl",
    ("download ", "wget ")                                  : "_download",
    ("port scan", "scan port", "open ports", "nmap")        : "_portscan",
    ("my ip", "public ip", "what is my ip", "external ip")  : "_myip",
    ("ip info", "lookup ip", "whois ip")                    : "_ipinfo",
    ("dns lookup", "nslookup", "resolve ")                  : "_dns",
    ("check url", "is site up", "is up", "site status")     : "_checkurl",
    ("local ip", "hostname", "my hostname")                 : "_localip",
    ("speed test", "internet speed")                        : "_speedtest",
}


class Plugin(PluginBase):
    priority = 30

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kws in _INTENTS for kw in kws)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        for kws, handler in _INTENTS.items():
            if any(kw in t for kw in kws):
                return getattr(self, handler)(text)
        return "Network: could not parse intent."

    # ------------------------------------------------------------------ #

    def _ping(self, text: str) -> str:
        host = self._arg(text, ("ping ",))
        if not host:
            return "Usage: ping <host>"
        host = host.split()[0]
        flag = "-n" if platform.system() == "Windows" else "-c"
        try:
            r = subprocess.run(
                ["ping", flag, "4", host],
                capture_output=True, text=True, timeout=10
            )
            lines = (r.stdout + r.stderr).strip().splitlines()
            # Return summary lines only
            summary = [l for l in lines if any(k in l.lower() for k in
                       ("packet", "loss", "avg", "rtt", "round", "ms", "transmitted"))]
            return "\n".join(summary) if summary else "\n".join(lines[-4:])
        except subprocess.TimeoutExpired:
            return f"{host} did not respond within 10s."
        except FileNotFoundError:
            return self._ping_py(host)

    def _ping_py(self, host: str) -> str:
        """Fallback: TCP connect to port 80 as reachability check."""
        try:
            start = time.time()
            socket.create_connection((host, 80), timeout=3)
            ms = int((time.time() - start) * 1000)
            return f"{host} is reachable (TCP:80, {ms}ms)"
        except Exception:
            return f"{host} is unreachable."

    def _curl(self, text: str) -> str:
        url = self._arg(text, ("curl ", "get ", "fetch url ", "http get "))
        if not url:
            return "Usage: curl <url>"
        url = url.split()[0]
        if not url.startswith("http"):
            url = "https://" + url
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read(4096).decode(errors="replace")
                status = r.status
            return f"HTTP {status}  {url}\n{body[:1500]}"
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code} {e.reason}  {url}"
        except Exception as e:
            return f"[error] {e}"

    def _download(self, text: str) -> str:
        url = self._arg(text, ("download ", "wget "))
        if not url:
            return "Usage: download <url>"
        url = url.split()[0]
        if not url.startswith("http"):
            url = "https://" + url
        filename = os.path.basename(urllib.parse.urlparse(url).path) or "download"
        dest = os.path.join(os.getcwd(), filename)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            start = time.time()
            with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                total = 0
                while chunk := r.read(65536):
                    f.write(chunk)
                    total += len(chunk)
            elapsed = round(time.time() - start, 2)
            return f"Downloaded '{filename}' ({total // 1024}KB) in {elapsed}s  →  {dest}"
        except Exception as e:
            return f"[error] {e}"

    def _portscan(self, text: str) -> str:
        """Scan common ports on a host."""
        t = text.lower()
        for kw in ("port scan ", "scan port ", "open ports ", "nmap "):
            if kw in t:
                host = text[t.index(kw) + len(kw):].strip().split()[0]
                break
        else:
            return "Usage: port scan <host>"

        common = [21, 22, 23, 25, 53, 80, 110, 143, 443,
                  465, 587, 993, 995, 3306, 3389, 5432, 6379,
                  8080, 8443, 8888, 27017]
        open_ports, closed = [], 0
        for port in common:
            try:
                s = socket.create_connection((host, port), timeout=0.5)
                s.close()
                # Try to grab service name
                try:
                    svc = socket.getservbyport(port)
                except Exception:
                    svc = "?"
                open_ports.append(f"  {port:<6} {svc}")
            except Exception:
                closed += 1
        if not open_ports:
            return f"No common ports open on {host}."
        return f"Open ports on {host}:\n" + "\n".join(open_ports) + f"\n({closed} closed)"

    def _myip(self, text: str) -> str:
        services = [
            "https://api.ipify.org",
            "https://ifconfig.me/ip",
            "https://icanhazip.com",
        ]
        for svc in services:
            try:
                req = urllib.request.Request(svc, headers={"User-Agent": "curl/7"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    return f"Public IP: {r.read().decode().strip()}"
            except Exception:
                continue
        return "Could not determine public IP."

    def _ipinfo(self, text: str) -> str:
        ip = self._arg(text, ("ip info ", "lookup ip ", "whois ip "))
        if not ip:
            return "Usage: ip info <ip or domain>"
        ip = ip.split()[0]
        try:
            url = f"https://ipinfo.io/{ip}/json"
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                import json
                data = json.loads(r.read())
            fields = ["ip", "city", "region", "country", "org", "timezone"]
            return "\n".join(f"{k}: {data.get(k, 'N/A')}" for k in fields)
        except Exception as e:
            return f"[error] {e}"

    def _dns(self, text: str) -> str:
        host = self._arg(text, ("dns lookup ", "nslookup ", "resolve "))
        if not host:
            return "Usage: dns lookup <hostname>"
        host = host.split()[0]
        try:
            results = socket.getaddrinfo(host, None)
            ips = list(dict.fromkeys(r[4][0] for r in results))
            return f"{host} resolves to:\n" + "\n".join(f"  {ip}" for ip in ips)
        except socket.gaierror as e:
            return f"DNS lookup failed for '{host}': {e}"

    def _checkurl(self, text: str) -> str:
        url = self._arg(text, ("check url ", "is site up ", "is up ", "site status "))
        if not url:
            return "Usage: check url <url>"
        url = url.split()[0]
        if not url.startswith("http"):
            url = "https://" + url
        try:
            start = time.time()
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                ms = int((time.time() - start) * 1000)
                return f"UP  HTTP {r.status}  {url}  ({ms}ms)"
        except urllib.error.HTTPError as e:
            return f"UP (with error)  HTTP {e.code}  {url}"
        except Exception:
            return f"DOWN  {url}  (unreachable)"

    def _localip(self, text: str) -> str:
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "unknown"
        return f"Hostname : {hostname}\nLocal IP : {local_ip}"

    def _speedtest(self, text: str) -> str:
        """Rough download speed estimate using a known test file."""
        url = "https://speed.cloudflare.com/__down?bytes=5000000"  # 5MB
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            start = time.time()
            total = 0
            with urllib.request.urlopen(req, timeout=20) as r:
                while chunk := r.read(65536):
                    total += len(chunk)
            elapsed = time.time() - start
            mbps = round((total * 8) / (elapsed * 1_000_000), 2)
            return f"Download speed: ~{mbps} Mbps  ({total // 1024}KB in {round(elapsed,2)}s)"
        except Exception as e:
            return f"[speedtest error] {e}"

    # ------------------------------------------------------------------ #

    @staticmethod
    def _arg(text: str, triggers: tuple) -> str:
        for trigger in triggers:
            if trigger.lower() in text.lower():
                idx = text.lower().index(trigger.lower()) + len(trigger)
                return text[idx:].strip()
        return ""
