from __future__ import annotations
import os


def gate(name: str, default: bool = False, settings: dict | None = None) -> bool:
    """
    Non-blocking gate check. Priority: env var > settings > default.
    Env var format: YIGTHINKER_GATE_<NAME_UPPER>=1|0
    """
    env_key = f"YIGTHINKER_GATE_{name.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val.strip().lower() not in ("0", "false", "no", "")

    if settings is not None:
        gates_cfg = settings.get("gates", {})
        if name in gates_cfg:
            return bool(gates_cfg[name])

    return default


async def gate_async(name: str, default: bool = False, settings: dict | None = None) -> bool:
    """Async gate check (reserved for remote gate service in commercial tier)."""
    return gate(name, default=default, settings=settings)
