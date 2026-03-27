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
    return load().get(key, default)


def get_llm_config() -> dict:
    """Returns the active LLM backend config merged with shared llm settings."""
    cfg = load()
    mode = os.environ.get("JARVIS_LLM_MODE") or cfg.get("llm_mode", "openai")
    backends = cfg.get("llm_backends", {})
    backend = dict(backends.get(mode, {}))

    # Env var overrides
    if os.environ.get("JARVIS_LLM_API_KEY"):
        backend["api_key"] = os.environ["JARVIS_LLM_API_KEY"]
    if os.environ.get("JARVIS_LLM_URL"):
        backend["base_url"] = os.environ["JARVIS_LLM_URL"]
    if os.environ.get("JARVIS_LLM_MODEL"):
        backend["model"] = os.environ["JARVIS_LLM_MODEL"]

    # Merge shared prompt config
    shared = cfg.get("llm", {})
    backend.setdefault("system_prompt", shared.get(
        "system_prompt",
        "You are Jarvis, a fast and helpful AI assistant. Be concise."
    ))
    backend["_mode"] = mode
    return backend
