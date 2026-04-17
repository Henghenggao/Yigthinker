from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "model": "claude-sonnet-4-20250514",
    "fallback_model": None,
    "planner": {"enabled": False, "trigger": "auto"},
    "permissions": {
        "mode": "default",
        "allow": [
            "df_load",
            "df_profile",
            "df_merge",
            "schema_inspect",
            "explore_overview",
            "explore_drilldown",
            "explore_anomaly",
            "chart_create",
            "chart_modify",
            "chart_recommend",
            "forecast_timeseries",
            "forecast_regression",
            "forecast_evaluate",
            "finance_calculate",
            "finance_analyze",
            "finance_validate",
        ],
        "ask": [],
        "deny": [],
    },
    "connections": {},
    "theme": {
        "number_format": "#,##0",
        "date_format": "%Y-%m-%d",
    },
    "advisor": {"enabled": False, "model": "haiku"},
    "voice": {"enabled": False, "language": "zh"},
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
        "behavior": True,   # Phase 10 — enables PatternStore + suggest_automation + BHV-01/02 directives
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
        "rpa": {
            "max_attempts_24h": 3,
            "max_llm_calls_day": 10,
            "db_path": "~/.yigthinker/rpa/state.db",
        },
    },
    "behavior": {
        "enabled": True,
        "health_check_threshold": {
            "alert_on_overdue": True,
            "alert_on_failure_rate_pct": 20.0,
        },
        "suggest_automation": {
            "enabled": True,
        },
    },
    "memory": {
        "provider": "null",   # "null" | "file". See docs/adr/005-memory-provider-interface.md
        "file": {
            "store_dir": None,   # None -> ~/.yigthinker/memory/
            "agent_id": "default",
            "max_records_before_compact": 1000,
        },
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
    "agent": {
        # Wall-clock budget for AgentLoop.run() overall. Individual channels
        # may override via `channel_timeouts` below; unspecified channels use
        # this default.
        "timeout_seconds": 300.0,
        # quick-260416-j3y-04: IM surfaces (Teams/Feishu/etc.) tolerate longer
        # waits than the CLI REPL because the user is async and expects a card
        # reply rather than a live cursor. 600s gives the model room to finish
        # multi-tool analyses on slower Ollama/Azure deployments.
        "channel_timeouts": {
            "teams": 600.0,
        },
    },
    "sandbox": {
        "df_transform": {
            "allowed_imports": ["pandas", "numpy", "polars"],
            "no_file_io": True,
            "no_network": True,
            "timeout_seconds": 60,
        }
    },
    "thinking": {
        "enabled": False,
        "budget_tokens": 10000,
    },
    "hooks": {
        "capabilities": {
            "inject_system": True,
            "suppress_output": True,
            "replace_result": True,
        },
    },
    "undo": {
        "max_stack_depth": 20,
    },
    "session": {
        "max_checkpoints": 10,
    },
}


def load_settings(
    project_dir: Path | None = None,
    user_dir: Path | None = None,
) -> dict[str, Any]:
    """Load and merge settings: defaults → project → user → managed (managed wins).

    Args:
        project_dir: Override for the project root (default: cwd).
        user_dir: Override for the user home directory (default: Path.home()).
                  Useful in tests to avoid reading the real ~/.yigthinker/settings.json.
    """
    import os

    settings = _deep_merge({}, DEFAULT_SETTINGS)

    # 1. Project level (.yigthinker/settings.json)
    project_path = (project_dir or Path.cwd()) / ".yigthinker" / "settings.json"
    if project_path.exists():
        settings = _deep_merge(settings, json.loads(project_path.read_text(encoding="utf-8")))

    # 2. User level (~/.yigthinker/settings.json)
    user_path = (user_dir or Path.home()) / ".yigthinker" / "settings.json"
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
