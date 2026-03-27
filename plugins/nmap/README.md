# nmap plugin

Run nmap scans via natural language and get formatted results.

## Example commands

```
scan example.com
nmap example.com
do a stealth scan on 192.168.1.1
check all ports on scanme.nmap.org
get service versions running on example.com
do a vulnerability scan on 10.0.0.1
quick scan example.com
```

## Scan modes

| Mode | Flags | Requires root |
|------|-------|---------------|
| normal (default) | `-T4 --open` | No |
| silent / stealth | `-sS -T2 --open` | Yes |
| full (all ports) | `-p- -T4 --open` | No |
| version detection | `-sV -T4 --open` | No |
| OS detection | `-O -T4` | Yes |
| vulnerability | `--script vuln -T4` | No |
| quick | `-F -T4 --open` | No |

## Adding a new mode

Add an entry to `_TRIGGER_MAP` and `_MODE_KEYWORDS` inside `plugin.py`. No other file needs to change.

## Prerequisites

```bash
sudo apt install nmap   # Debian/Ubuntu
brew install nmap       # macOS
```
