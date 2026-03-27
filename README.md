# J.A.R.V.I.S

> Just A Rather Very Intelligent System

A lightweight, modular agentic AI assistant built for speed, low memory usage, and portability across devices.

## Philosophy
- **Fast** — minimal overhead, no bloat
- **Modular** — every feature is a plugin, zero core changes needed
- **Portable** — runs on low-resource devices (RPi, old laptops, servers)
- **Extensible** — drop a file in `plugins/` to add a new skill

## Structure
```
jarvis/
├── main.py              # Entrypoint
├── core/
│   ├── agent.py         # Main agent loop
│   ├── dispatcher.py    # Routes intents to plugins
│   ├── memory.py        # Short-term session memory
│   └── config.py        # Config loader
├── plugins/
│   ├── base.py          # Plugin base class
│   └── hello/
│       └── plugin.py    # Example plugin
├── config.yaml          # User configuration
└── requirements.txt
```

## Quickstart
```bash
pip install -r requirements.txt
python main.py
```

## Adding a Plugin
1. Create `plugins/yourskill/plugin.py`
2. Subclass `PluginBase` and implement `matches()` and `run()`
3. Drop it in — auto-discovered on startup, no core changes
