"""Tests for session hibernation (serialize/deserialize to disk)."""
import json
import pickle

import pandas as pd
import pytest

from yigthinker.presence.gateway.hibernation import SessionHibernator
from yigthinker.presence.gateway.session_registry import ManagedSession
from yigthinker.session import SessionContext
from yigthinker.types import Message


@pytest.mark.asyncio
async def test_hibernate_and_restore(tmp_path):
    """Full round-trip: create session with DataFrame → hibernate → restore."""
    hibernator = SessionHibernator(tmp_path)

    # Create a session with data
    ctx = SessionContext(settings={"model": "test"})
    ctx.vars.set("revenue", pd.DataFrame({
        "month": ["Jan", "Feb", "Mar"],
        "amount": [100, 200, 300],
    }))
    ctx.messages = [
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi there"),
    ]

    session = ManagedSession(key="test:user1", ctx=ctx, channel_origin="test")

    # Hibernate
    session_dir = await hibernator.save(session)
    assert session_dir.exists()

    # Restore
    restored = await hibernator.load("test:user1", {"model": "test"})
    assert restored is not None
    assert restored.key == "test:user1"
    assert restored.channel_origin == "test"

    # Verify DataFrame
    df = restored.ctx.vars.get("revenue")
    assert isinstance(df, pd.DataFrame)
    assert df.shape == (3, 2)
    assert list(df["month"]) == ["Jan", "Feb", "Mar"]

    # Verify messages restored
    assert len(restored.ctx.messages) >= 2

    # Hibernation dir should be cleaned up
    assert not session_dir.exists()


@pytest.mark.asyncio
async def test_hibernate_nonexistent_session(tmp_path):
    """Restoring a non-existent session returns None."""
    hibernator = SessionHibernator(tmp_path)
    result = await hibernator.load("nonexistent:key", {})
    assert result is None


@pytest.mark.asyncio
async def test_has_hibernated(tmp_path):
    hibernator = SessionHibernator(tmp_path)
    assert not hibernator.has_hibernated("test:user1")

    ctx = SessionContext(settings={})
    session = ManagedSession(key="test:user1", ctx=ctx)
    await hibernator.save(session)
    assert hibernator.has_hibernated("test:user1")


@pytest.mark.asyncio
async def test_hibernate_string_var(tmp_path):
    """String variables (e.g., chart JSON) survive hibernation."""
    hibernator = SessionHibernator(tmp_path)

    ctx = SessionContext(settings={})
    ctx.vars.set("chart_data", '{"type": "bar", "data": [1, 2, 3]}')
    session = ManagedSession(key="test:user1", ctx=ctx)

    await hibernator.save(session)
    restored = await hibernator.load("test:user1", {})

    assert restored is not None
    chart = restored.ctx.vars.get("chart_data")
    assert '"bar"' in chart


@pytest.mark.asyncio
async def test_hibernate_dataframe_falls_back_to_table_json(tmp_path, monkeypatch):
    """Unsafe pickle fallback is replaced with a table-JSON round-trip."""
    hibernator = SessionHibernator(tmp_path)

    ctx = SessionContext(settings={})
    ctx.vars.set("mixed_df", pd.DataFrame({
        "id": [1, 2],
        "payload": [{"region": "N"}, {"region": "S"}],
    }))
    session = ManagedSession(key="test:user-json", ctx=ctx)

    def _fail_to_parquet(self, *args, **kwargs):
        raise RuntimeError("forced parquet failure for test")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", _fail_to_parquet)

    await hibernator.save(session)
    restored = await hibernator.load("test:user-json", {})

    assert restored is not None
    restored_df = restored.ctx.vars.get("mixed_df")
    assert list(restored_df["id"]) == [1, 2]
    assert restored_df["payload"].iloc[0]["region"] == "N"


@pytest.mark.asyncio
async def test_legacy_pickle_restore_is_blocked_by_default(tmp_path):
    """Legacy pickle manifests are ignored unless explicitly opted in."""
    hibernator = SessionHibernator(tmp_path)

    session = ManagedSession(key="test:legacy", ctx=SessionContext(settings={}))
    session_dir = await hibernator.save(session)
    vars_dir = session_dir / "vars"

    with open(vars_dir / "legacy.pickle", "wb") as f:
        pickle.dump({"safe": True}, f, protocol=5)

    (session_dir / "manifest.json").write_text(
        json.dumps({
            "legacy": {
                "format": "pickle",
                "file": "legacy.pickle",
                "var_type": "artifact",
            }
        }),
        encoding="utf-8",
    )

    restored = await hibernator.load("test:legacy", {})
    assert restored is not None
    with pytest.raises(KeyError):
        restored.ctx.vars.get("legacy")


@pytest.mark.asyncio
async def test_hibernation_manifest_rejects_path_traversal(tmp_path):
    hibernator = SessionHibernator(tmp_path)

    session = ManagedSession(key="test:traversal", ctx=SessionContext(settings={}))
    session_dir = await hibernator.save(session)
    outside = session_dir.parent / "outside.json"
    outside.write_text("should-not-load", encoding="utf-8")

    (session_dir / "manifest.json").write_text(
        json.dumps({
            "escape": {
                "format": "json",
                "file": "../outside.json",
                "var_type": "artifact",
            }
        }),
        encoding="utf-8",
    )

    restored = await hibernator.load("test:traversal", {})
    assert restored is not None
    with pytest.raises(KeyError):
        restored.ctx.vars.get("escape")
