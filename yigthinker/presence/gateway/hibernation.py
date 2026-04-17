"""Session hibernation: serialize/deserialize SessionContext to disk."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from yigthinker.presence.gateway.session_registry import ManagedSession
from yigthinker.persistence import TranscriptReader, TranscriptWriter
from yigthinker.core.session import SessionContext

logger = logging.getLogger(__name__)


class SessionHibernator:
    """Persist and restore ManagedSession state to/from disk.

    Layout::

        {hibernate_dir}/{key_hash}/
            metadata.json
            messages.jsonl
            stats.json
            vars/
                revenue.parquet
                forecast.parquet
                chart_q1.json
    """

    def __init__(self, hibernate_dir: Path) -> None:
        self._dir = hibernate_dir.expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, session: ManagedSession) -> Path:
        """Serialize a session to disk. Returns the session directory."""
        session_dir = self._session_dir(session.key)
        session_dir.mkdir(parents=True, exist_ok=True)
        vars_dir = session_dir / "vars"
        vars_dir.mkdir(exist_ok=True)

        # 1. Metadata
        metadata = {
            "session_id": session.ctx.session_id,
            "key": session.key,
            "channel_origin": session.channel_origin,
            "created_at": session.created_at,
            "last_active": session.last_active,
            "ctx_created_at": session.ctx.created_at,
            "ctx_last_active": session.ctx.last_active,
            "transcript_path": session.ctx.transcript_path,
            "settings_hash": _hash_settings(session.ctx.settings),
        }
        (session_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # 2. Messages (JSONL — reuse existing TranscriptWriter format)
        messages_path = session_dir / "messages.jsonl"
        writer = TranscriptWriter(messages_path)
        for msg in session.ctx.messages:
            writer.append(msg.role, msg.content)

        # 3. Stats
        (session_dir / "stats.json").write_text(
            json.dumps(session.ctx.stats.to_dict(), indent=2), encoding="utf-8"
        )

        # 4. Variables
        manifest: dict[str, dict[str, Any]] = {}
        for name, var_entry in session.ctx.vars._vars.items():
            value = var_entry.value if hasattr(var_entry, "value") else var_entry
            var_type = getattr(var_entry, "var_type", "dataframe")
            entry = _save_var(name, value, vars_dir)
            entry["var_type"] = var_type
            manifest[name] = entry

        (session_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        return session_dir

    async def load(self, key: str, settings: dict[str, Any]) -> ManagedSession | None:
        """Restore a session from disk. Returns None if not found."""
        session_dir = self._session_dir(key)
        if not session_dir.exists():
            return None

        # 1. Metadata
        metadata = json.loads(
            (session_dir / "metadata.json").read_text(encoding="utf-8")
        )

        current_hash = _hash_settings(settings)
        if metadata.get("settings_hash") != current_hash:
            logger.warning("Settings changed since session %s was hibernated", key)

        # 2. Messages
        messages_path = session_dir / "messages.jsonl"
        messages = TranscriptReader(messages_path).to_messages() if messages_path.exists() else []

        # 3. Stats
        stats_path = session_dir / "stats.json"
        stats_data = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}

        # 4. Variables
        manifest_path = session_dir / "manifest.json"
        vars_dir = session_dir / "vars"

        ctx = SessionContext(
            session_id=metadata["session_id"],
            settings=settings,
            transcript_path=metadata.get("transcript_path", ""),
            created_at=metadata.get("ctx_created_at", time.time()),
            last_active=metadata.get("ctx_last_active", time.time()),
            channel_origin=metadata.get("channel_origin", "cli"),
            messages=messages,
        )

        # Restore stats
        connection_usage = stats_data.pop("connection_usage", {})
        top_tables = stats_data.pop("top_tables", {})
        ctx.stats._counters = defaultdict(int, stats_data)
        ctx.stats._connection_usage = defaultdict(int, connection_usage)
        ctx.stats._top_tables = defaultdict(int, top_tables)

        # Restore variables
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for name, entry in manifest.items():
                value = _load_var(name, entry, vars_dir)
                if value is not None:
                    var_type = entry.get("var_type", "dataframe")
                    ctx.vars.set(name, value, var_type=var_type)

        try:
            session = ManagedSession(
                key=key,
                ctx=ctx,
                created_at=metadata.get("created_at", time.monotonic()),
                last_active=time.monotonic(),
                channel_origin=metadata.get("channel_origin", "cli"),
            )
            session.ctx.mark_active()
        except Exception:
            logger.exception("Failed to construct ManagedSession for %s; hibernation data preserved", key)
            return None

        # Clean up hibernation files only after successful session construction
        _rmtree(session_dir)

        return session

    def has_hibernated(self, key: str) -> bool:
        return self._session_dir(key).exists()

    def _session_dir(self, key: str) -> Path:
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self._dir / key_hash


# ── Variable serialization ───────────────────────────────────────────────────

def _save_var(name: str, value: Any, vars_dir: Path) -> dict[str, Any]:
    """Save a single variable. Returns manifest entry."""
    if isinstance(value, pd.DataFrame):
        path = vars_dir / f"{name}.parquet"
        try:
            value.to_parquet(path, engine="pyarrow", compression="snappy")
            return {"format": "parquet", "file": path.name, "shape": list(value.shape)}
        except Exception:
            # Mixed-type/object columns can fail with parquet; use table JSON as a
            # safe fallback instead of pickle to avoid arbitrary-code deserialization.
            logger.warning("Parquet failed for '%s', falling back to table JSON", name)
            try:
                path = vars_dir / f"{name}.table.json"
                path.write_text(
                    value.to_json(orient="table", date_format="iso"),
                    encoding="utf-8",
                )
                return {"format": "table_json", "file": path.name, "shape": list(value.shape)}
            except Exception:
                logger.warning(
                    "Skipping dataframe '%s' during hibernation after parquet/JSON failure.",
                    name,
                )
                return {
                    "format": "unsupported",
                    "python_type": type(value).__name__,
                    "shape": list(value.shape),
                }

    if isinstance(value, str):
        path = vars_dir / f"{name}.json"
        path.write_text(value, encoding="utf-8")
        return {"format": "json", "file": path.name}

    if _is_json_serializable(value):
        path = vars_dir / f"{name}.value.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"format": "json_value", "file": path.name}

    logger.warning(
        "Skipping unsupported variable '%s' during hibernation (type=%s).",
        name,
        type(value).__name__,
    )
    return {"format": "unsupported", "python_type": type(value).__name__}


def _load_var(name: str, entry: dict[str, Any], vars_dir: Path) -> Any:
    """Load a single variable from its manifest entry."""
    fmt = entry.get("format", "")
    path = _resolve_var_path(name, entry, vars_dir)
    if path is None:
        if fmt == "unsupported":
            logger.warning(
                "Skipping unsupported hibernated variable '%s' (type=%s)",
                name,
                entry.get("python_type", "unknown"),
            )
        return None

    if fmt == "parquet":
        return pd.read_parquet(path, engine="pyarrow")
    if fmt == "table_json":
        return pd.read_json(
            StringIO(path.read_text(encoding="utf-8")),
            orient="table",
        )
    if fmt == "json":
        return path.read_text(encoding="utf-8")
    if fmt == "json_value":
        return json.loads(path.read_text(encoding="utf-8"))
    if fmt == "pickle":
        logger.warning(
            "Blocked legacy pickle restore for variable '%s'. "
            "Delete the hibernation data and regenerate it with a newer version.",
            name,
        )
        return None

    logger.warning("Unknown format '%s' for variable '%s'", fmt, name)
    return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hash_settings(settings: dict[str, Any]) -> str:
    raw = json.dumps(settings, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return True


def _resolve_var_path(name: str, entry: dict[str, Any], vars_dir: Path) -> Path | None:
    file_name = entry.get("file", "")
    if not file_name:
        logger.warning("Variable '%s' manifest has no file entry", name)
        return None

    if Path(file_name).name != file_name:
        logger.warning(
            "Rejected path traversal in hibernation manifest for variable '%s': %s",
            name,
            file_name,
        )
        return None

    path = vars_dir / file_name
    resolved_path = path.resolve(strict=False)
    resolved_vars_dir = vars_dir.resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_vars_dir):
        logger.warning(
            "Rejected out-of-tree hibernation path for variable '%s': %s",
            name,
            file_name,
        )
        return None

    if not path.exists():
        logger.warning("Variable file missing: %s", path)
        return None

    return path


def _rmtree(path: Path) -> None:
    """Remove a directory tree (best-effort)."""
    import shutil
    try:
        shutil.rmtree(path)
    except OSError:
        logger.warning("Could not remove hibernate dir: %s", path)
