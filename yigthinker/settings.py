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
    "dashboard_url": "http://localhost:8765",
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
    settings = _deep_merge({}, DEFAULT_SETTINGS)

    # 1. Project level (.yigthinker/settings.json)
    project_path = (project_dir or Path.cwd()) / ".yigthinker" / "settings.json"
    if project_path.exists():
        settings = _deep_merge(settings, json.loads(project_path.read_text(encoding="utf-8")))

    # 2. User level (~/.yigthinker/settings.json)
    user_path = Path.home() / ".yigthinker" / "settings.json"
    if user_path.exists():
        settings = _deep_merge(settings, json.loads(user_path.read_text(encoding="utf-8")))

    # 3. Managed level (highest priority — enterprise lockdown)
    managed_path = Path("/etc/yigthinker/settings.json")
    if managed_path.exists():
        settings = _deep_merge(settings, json.loads(managed_path.read_text(encoding="utf-8")))

    return settings


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base. Override wins on conflicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
