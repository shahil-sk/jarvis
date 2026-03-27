# Launcher / Workspace Manager Plugin

Open apps, files, and URLs individually or as named workspace bundles.

## Setup

Define workspaces in `config.yaml`:

```yaml
jarvis:
  workspaces:
    dev:
      - code                          # VS Code
      - https://github.com/shahil-sk
      - ~/projects
      - firefox

    work:
      - https://mail.google.com
      - https://calendar.google.com
      - notion
      - slack

    music:
      - spotify
      - https://soundcloud.com

    monitor:
      - htop                          # terminal app (run htop instead)
      - https://grafana.myserver.com
```

## Commands

```
workspace dev          → opens all dev items
switch to work         → opens all work items
dev                    → shorthand (just the name)
list workspaces        → shows all defined workspaces + items
```

## Item Types (auto-detected)
| Item | Detected as |
|---|---|
| `https://...` | Opens in default browser |
| `~/path` or `/path` | Opens file/folder |
| anything else | Treated as app name |
