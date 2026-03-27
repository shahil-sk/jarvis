# Network Plugin

All commands use **stdlib only** (`socket`, `urllib`). No extra deps.

## Commands

| You say | What it does |
|---|---|
| `ping google.com` | ICMP ping (4 packets, summary) |
| `curl https://example.com` | HTTP GET, returns first 1.5KB |
| `download https://example.com/file.zip` | Downloads to CWD |
| `port scan 192.168.1.1` | Checks 21 common ports via TCP |
| `my ip` | Your public IP (ipify/ifconfig.me) |
| `ip info 8.8.8.8` | City, region, org, timezone (ipinfo.io) |
| `dns lookup github.com` | Resolves hostname to IPs |
| `check url https://mysite.com` | HEAD request, UP/DOWN + latency |
| `local ip` | Hostname + LAN IP |
| `speed test` | ~Download speed via Cloudflare 5MB test |

## Notes
- Port scan uses 0.5s timeout per port — fast but not exhaustive
- Speed test is a rough estimate, not a full duplex test
- `curl` output is capped at 1500 chars
