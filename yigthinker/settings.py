from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "model": "claude-sonnet-4-20250514",
    "fallback_model": None,
    "planner": {"enabled": False, "trigger": "auto"},
    "permissions": {"allow": [], "ask": [], "deny": []},
    "connections": {},
    "theme": {
        "number_format": "#,##0",
        "date_format": "%Y-%m-%d",
    },
    "advisor": {"enabled": False, "model": "haiku"},
    "voice": {"enabled": False, "language": "zh"},
    "dashboard_url": "http://localhost:8766",
    "ollama_base_url": "http://localhost:11434",
    "azure_endpoint": "",
    "azure_api_version": "2024-02-01",
    "gates": {
        "session_memory": True,
        "auto_dream": True,
        "speculation": False,
        "agent_teams": True,
        "advisor": False,
        "voice": False,
    },
    "gateway": {
        "host": "127.0.0.1",
        "port": 8766,
        "idle_timeout_seconds": 3600,
        "max_sessions": 100,
        "hibernate_dir": "~/.yigthinker/hibernate",
        "max_hibernate_size_mb": 500,
        "session_scope": "per-sender",
        "eviction_interval_seconds": 60,
    },
    "channels": {
        "feishu": {
            "enabled": False,
            "app_id": "",
            "app_secret": "",
            "verification_token": "",
            "session_scope": "per-sender",
            "dedup_ttl_seconds": 3600,
        },
        "teams": {
            "enabled": False,
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "webhook_secret": "",
            "session_scope": "per-sender",
            "service_url": "",
            "max_retries": 3,
            "timeout": 30.0,
        },
        "gchat": {
            "enabled": False,
            "service_account_key_path": "",
            "project_number": "",
            "session_scope": "per-sender",
        },
    },
    "spawn_agent": {
        "max_concurrent": 3,
        "max_iterations": 20,
        "timeout": 120.0,
    },
    "sandbox": {
        "df_transform": {
            "allowed_imports": ["pandas", "numpy", "polars"],
            "no_file_io": True,
            "no_network": True,
            "timeout_seconds": 60,
        }
    },
}


def load_settings(project_dir: Path | None = None) -> dict[str, Any]:
    """Load and merge settings: defaults → project → user → managed (managed wins)."""
    import os

    settings = _deep_merge({}, DEFAULT_SETTINGS)

    # 1. Project level (.yigthinker/settings.json)
    project_path = (project_dir or Path.cwd()) / ".yigthinker" / "settings.json"
    if project_path.exists():
        settings = _deep_merge(settings, json.loads(project_path.read_text(encoding="utf-8")))

    # 2. User level (~/.yigthinker/settings.json)
    user_path = Path.home() / ".yigthinker" / "settings.json"
    if user_path.exists():
        user_data = json.loads(user_path.read_text(encoding="utf-8"))
        settings = _deep_merge(settings, user_data)

        # Promote saved API keys into environment so providers can pick them up.
        for env_var in ("anthropic_api_key", "openai_api_key", "azure_openai_api_key"):
            if env_var in user_data and not os.environ.get(env_var.upper()):
                os.environ[env_var.upper()] = user_data[env_var]

    # 3. Managed level (highest priority — enterprise lockdown)
    managed_path = Path("/etc/yigthinker/settings.json")
    if managed_path.exists():
        settings = _deep_merge(settings, json.loads(managed_path.read_text(encoding="utf-8")))

    return settings


def has_api_key(settings: dict[str, Any]) -> bool:
    """Return True if a usable API key is available for the configured model."""
    import os

    model = settings.get("model", "")
    if model.startswith("claude"):
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return bool(os.environ.get("OPENAI_API_KEY"))
    if model.startswith("azure/"):
        return bool(os.environ.get("AZURE_OPENAI_API_KEY"))
    if model.startswith("ollama/"):
        return True  # no key needed
    return False


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base. Override wins on conflicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
