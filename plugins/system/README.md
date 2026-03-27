# System Plugin

Handles OS-level tasks. Priority 10 — runs before LLM.

## Supported Commands

| What you say | What it does |
|---|---|
| `cpu` / `ram` / `stats` | CPU, RAM, Disk usage (needs `psutil`) |
| `uptime` | Jarvis session uptime |
| `os` / `system info` | OS, arch, Python version |
| `run <cmd>` / `$ <cmd>` | Execute a shell command |
| `open <app>` / `launch <app>` | Open app/file cross-platform |

## Optional Dependency
```bash
pip install psutil  # for CPU/RAM/disk stats
```

## Safety
Destructive patterns (`rm -rf /`, `mkfs`, etc.) are blocked at the plugin level.
