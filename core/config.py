"""Config loader — reads config.yaml once at startup."""

import yaml
import os

_cfg = None

def load(path: str = "config.yaml") -> dict:
    global _cfg
    if _cfg is not None:
        return _cfg
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r") as f:
        _cfg = yaml.safe_load(f).get("jarvis", {})
    return _cfg

def get(key: str, default=None):
    cfg = load()
    return cfg.get(key, default)
