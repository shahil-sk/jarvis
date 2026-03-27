"""Network plugin — ping, curl, download, portscan, IP info, DNS, speedtest, traceroute, whois."""

import socket
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import platform
import os
import re
import time
from plugins.base import PluginBase, PluginCapability


class Plugin(PluginBase):
    priority = 30

    capabilities = [
        PluginCapability(
            intent="net.ping",
            description="Ping a host and show latency",
            args={"host": "str"},
            trigger_template="ping {host}",
            examples=[
                ("ping google.com", {"host": "google.com"}),
                ("is 192.168.1.1 reachable", {"host": "192.168.1.1"}),
            ],
        ),
        PluginCapability(
            intent="net.curl",
            description="Make an HTTP GET request and show the response",
            args={"url": "str"},
            trigger_template="curl {url}",
            examples=[
                ("curl https://httpbin.org/get", {"url": "https://httpbin.org/get"}),
                ("fetch url api.github.com", {"url": "https://api.github.com"}),
            ],
        ),
        PluginCapability(
            intent="net.download",
            description="Download a file from a URL",
            args={"url": "str"},
            trigger_template="download {url}",
            examples=[
                ("download https://example.com/file.zip", {"url": "https://example.com/file.zip"}),
            ],
        ),
        PluginCapability(
            intent="net.myip",
            description="Show my public IP address",
            args={},
            trigger_template="my public ip",
            examples=[("what is my ip", {}), ("show public ip", {}), ("external ip", {})],
        ),
        PluginCapability(
            intent="net.localip",
            description="Show local hostname and IP address",
            args={},
            trigger_template="my local ip",
            examples=[("local ip", {}), ("my hostname", {})],
        ),
        PluginCapability(
            intent="net.ipinfo",
            description="Get geolocation and ISP info for an IP address",
            args={"ip": "str"},
            trigger_template="ip info {ip}",
            examples=[
                ("ip info 8.8.8.8", {"ip": "8.8.8.8"}),
                ("whois ip 1.1.1.1", {"ip": "1.1.1.1"}),
            ],
        ),
        PluginCapability(
            intent="net.dns",
            description="DNS lookup for a hostname",
            args={"host": "str"},
            trigger_template="dns {host}",
            examples=[
                ("dns lookup google.com", {"host": "google.com"}),
                ("resolve example.com", {"host": "example.com"}),
            ],
        ),
        PluginCapability(
            intent="net.checkurl",
            description="Check if a website is up or down",
            args={"url": "str"},
            trigger_template="check url {url}",
            examples=[
                ("is github down", {"url": "https://github.com"}),
                ("check if google.com is up", {"url": "https://google.com"}),
            ],
        ),
        PluginCapability(
            intent="net.speedtest",
            description="Measure internet download speed",
            args={},
            trigger_template="speed test",
            examples=[("speed test", {}), ("how fast is my internet", {})],
        ),
        PluginCapability(
            intent="net.traceroute",
            description="Trace network hops to a host",
            args={"host": "str"},
            trigger_template="traceroute {host}",
            examples=[
                ("traceroute google.com", {"host": "google.com"}),
                ("trace route to 8.8.8.8", {"host": "8.8.8.8"}),
            ],
        ),
        PluginCapability(
            intent="net.headers",
            description="Show HTTP response headers for a URL",
            args={"url": "str"},
            trigger_template="headers {url}",
            examples=[
                ("show headers for github.com", {"url": "https://github.com"}),
                ("http headers example.com", {"url": "https://example.com"}),
            ],
        ),
        PluginCapability(
            intent="net.interfaces",
            description="List network interfaces and their IP addresses",
            args={},
            trigger_template="network interfaces",
            examples=[("show network interfaces", {}), ("list network adapters", {})],
        ),
    ]

    def matches(self, text: str) -> bool:
        keywords = (
            "ping ", "curl ", "get ", "fetch url", "http get",
            "download ", "wget ", "my ip", "public ip", "what is my ip",
            "external ip", "ip info", "lookup ip", "whois ip",
            "dns lookup", "nslookup", "resolve ", "check url",
            "is site up", "is up", "site status", "local ip",
            "hostname", "my hostname", "speed test", "internet speed",
            "traceroute", "trace route", "headers ", "network interface",
            "network adapter",
        )
        t = text.lower()
        return any(kw in t for kw in keywords)

    def run(self, text: str, memory) -> str:
        t = text.lower()
        if "ping " in t:                                      return self._ping(text)
        if any(k in t for k in ("curl ", "fetch url", "http get")): return self._curl(text)
        if "download " in t or "wget " in t:                  return self._download(text)
        if any(k in t for k in ("my ip", "public ip", "external ip", "what is my ip")): return self._myip()
        if any(k in t for k in ("local ip", "my hostname", "hostname")):  return self._localip()
        if any(k in t for k in ("ip info", "lookup ip", "whois ip")):     return self._ipinfo(text)
        if any(k in t for k in ("dns", "nslookup", "resolve ")):          return self._dns(text)
        if any(k in t for k in ("check url", "is site up", "is up", "site status")): return self._checkurl(text)
        if any(k in t for k in ("speed test", "internet speed")):         return self._speedtest()
        if "traceroute" in t or "trace route" in t:          return self._traceroute(text)
        if "header" in t:                                    return self._headers(text)
        if any(k in t for k in ("network interface", "network adapter")):  return self._interfaces()
        return "Network: could not parse intent."

    def run_intent(self, intent: str, args: dict) -> str:
        dispatch = {
            "net.ping"       : lambda: self._ping(f"ping {args.get('host', '')}"),
            "net.curl"       : lambda: self._curl(f"curl {args.get('url', '')}"),
            "net.download"   : lambda: self._download(f"download {args.get('url', '')}"),
            "net.myip"       : lambda: self._myip(),
            "net.localip"    : lambda: self._localip(),
            "net.ipinfo"     : lambda: self._ipinfo(f"ip info {args.get('ip', '')}"),
            "net.dns"        : lambda: self._dns(f"resolve {args.get('host', '')}"),
            "net.checkurl"   : lambda: self._checkurl(f"check url {args.get('url', '')}"),
            "net.speedtest"  : lambda: self._speedtest(),
            "net.traceroute" : lambda: self._traceroute(f"traceroute {args.get('host', '')}"),
            "net.headers"    : lambda: self._headers(f"headers {args.get('url', '')}"),
            "net.interfaces" : lambda: self._interfaces(),
        }
        fn = dispatch.get(intent)
        return fn() if fn else f"Unknown net intent: {intent}"

    def _ping(self, text: str) -> str:
        host = _arg(text, ("ping ",)).split()[0] if _arg(text, ("ping ",)) else ""
        if not host:
            return "Usage: ping <host>"
        flag = "-n" if platform.system() == "Windows" else "-c"
        try:
            r = subprocess.run(["ping", flag, "4", host], capture_output=True, text=True, timeout=10)
            lines = (r.stdout + r.stderr).strip().splitlines()
            summary = [l for l in lines if any(k in l.lower() for k in
                       ("packet", "loss", "avg", "rtt", "round", "ms", "transmitted"))]
            return "\n".join(summary) if summary else "\n".join(lines[-4:])
        except subprocess.TimeoutExpired:
            return f"{host} did not respond within 10s."
        except FileNotFoundError:
            return self._ping_py(host)

    def _ping_py(self, host: str) -> str:
        try:
            start = time.time()
            socket.create_connection((host, 80), timeout=3)
            ms = int((time.time() - start) * 1000)
            return f"{host} is reachable (TCP:80, {ms}ms)"
        except Exception:
            return f"{host} is unreachable."

    def _curl(self, text: str) -> str:
        url = _arg(text, ("curl ", "get ", "fetch url ", "http get ")).split()[0]
        if not url:
            return "Usage: curl <url>"
        if not url.startswith("http"):
            url = "https://" + url
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body   = r.read(8192).decode(errors="replace")
                status = r.status
                ctype  = r.headers.get("Content-Type", "")
            return f"HTTP {status}  {url}\nContent-Type: {ctype}\n\n{body[:2000]}"
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code} {e.reason}  {url}"
        except Exception as e:
            return f"[error] {e}"

    def _download(self, text: str) -> str:
        url = _arg(text, ("download ", "wget ")).split()[0]
        if not url:
            return "Usage: download <url>"
        if not url.startswith("http"):
            url = "https://" + url
        filename = os.path.basename(urllib.parse.urlparse(url).path) or "download"
        dest = os.path.join(os.getcwd(), filename)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            start = time.time()
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                total = 0
                while chunk := r.read(65536):
                    f.write(chunk)
                    total += len(chunk)
            elapsed = round(time.time() - start, 2)
            return f"Downloaded '{filename}'  {total // 1024}KB  in {elapsed}s  ->  {dest}"
        except Exception as e:
            return f"[error] {e}"

    def _myip(self) -> str:
        for svc in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
            try:
                req = urllib.request.Request(svc, headers={"User-Agent": "curl/7"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    return f"Public IP: {r.read().decode().strip()}"
            except Exception:
                continue
        return "Could not determine public IP."

    def _localip(self) -> str:
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "unknown"
        return f"Hostname : {hostname}\nLocal IP : {local_ip}"

    def _ipinfo(self, text: str) -> str:
        ip = _arg(text, ("ip info ", "lookup ip ", "whois ip ")).split()[0]
        if not ip:
            return "Usage: ip info <ip>"
        try:
            import json
            req = urllib.request.Request(f"https://ipinfo.io/{ip}/json",
                                         headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read())
            return "\n".join(f"{k}: {d.get(k, 'N/A')}" for k in
                             ("ip", "hostname", "city", "region", "country", "org", "timezone"))
        except Exception as e:
            return f"[error] {e}"

    def _dns(self, text: str) -> str:
        host = _arg(text, ("dns lookup ", "nslookup ", "resolve ", "dns ")).split()[0]
        if not host:
            return "Usage: dns lookup <hostname>"
        try:
            results = socket.getaddrinfo(host, None)
            ips = list(dict.fromkeys(r[4][0] for r in results))
            return f"{host} resolves to:\n" + "\n".join(f"  {ip}" for ip in ips)
        except socket.gaierror as e:
            return f"DNS lookup failed for '{host}': {e}"

    def _checkurl(self, text: str) -> str:
        url = _arg(text, ("check url ", "is site up ", "is up ", "site status ")).split()[0]
        if not url:
            return "Usage: check url <url>"
        if not url.startswith("http"):
            url = "https://" + url
        try:
            start = time.time()
            req   = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                ms = int((time.time() - start) * 1000)
                return f"UP  HTTP {r.status}  {url}  ({ms}ms)"
        except urllib.error.HTTPError as e:
            return f"UP (with error)  HTTP {e.code}  {url}"
        except Exception:
            return f"DOWN  {url}"

    def _speedtest(self) -> str:
        url = "https://speed.cloudflare.com/__down?bytes=10000000"  # 10MB
        try:
            req   = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            start = time.time()
            total = 0
            with urllib.request.urlopen(req, timeout=30) as r:
                while chunk := r.read(65536):
                    total += len(chunk)
            elapsed = time.time() - start
            mbps    = round((total * 8) / (elapsed * 1_000_000), 2)
            return f"Download speed: ~{mbps} Mbps  ({total // 1024}KB in {round(elapsed,2)}s)"
        except Exception as e:
            return f"[speedtest error] {e}"

    def _traceroute(self, text: str) -> str:
        host = _arg(text, ("traceroute ", "trace route to ", "tracert ")).split()[0]
        if not host:
            return "Usage: traceroute <host>"
        cmd = ["tracert", host] if platform.system() == "Windows" else ["traceroute", "-m", "20", host]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return (r.stdout + r.stderr).strip()[:3000]
        except FileNotFoundError:
            return "traceroute not installed. Run: sudo apt install traceroute"
        except subprocess.TimeoutExpired:
            return "Traceroute timed out."
        except Exception as e:
            return f"[error] {e}"

    def _headers(self, text: str) -> str:
        url = _arg(text, ("headers ", "http headers ", "show headers for ")).split()[0]
        if not url:
            return "Usage: headers <url>"
        if not url.startswith("http"):
            url = "https://" + url
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                lines = [f"HTTP {r.status}  {url}"]
                for k, v in r.headers.items():
                    lines.append(f"{k}: {v}")
                return "\n".join(lines)
        except urllib.error.HTTPError as e:
            lines = [f"HTTP {e.code}  {url}"]
            for k, v in e.headers.items():
                lines.append(f"{k}: {v}")
            return "\n".join(lines)
        except Exception as e:
            return f"[error] {e}"

    def _interfaces(self) -> str:
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            lines = []
            for iface, addr_list in sorted(addrs.items()):
                stat = stats.get(iface)
                up   = "UP" if stat and stat.isup else "DOWN"
                lines.append(f"{iface}  ({up})")
                for a in addr_list:
                    lines.append(f"  {a.family.name:<10}  {a.address}")
            return "\n".join(lines)
        except ImportError:
            return self._interfaces_fallback()

    def _interfaces_fallback(self) -> str:
        cmd = ["ipconfig"] if platform.system() == "Windows" else ["ip", "addr"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.stdout.strip()[:3000]
        except Exception as e:
            return f"[error] {e}"


def _arg(text: str, triggers: tuple) -> str:
    for t in triggers:
        if t.lower() in text.lower():
            idx = text.lower().index(t.lower()) + len(t)
            return text[idx:].strip()
    return ""
