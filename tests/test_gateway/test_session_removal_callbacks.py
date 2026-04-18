"""Tests for SessionRegistry session-removal callbacks.

Motivation: before 2026-04-17 the gateway's PermissionSystem accumulated
per-session overrides forever because session eviction / hibernation /
shutdown never called `PermissionSystem.clear_session(session_id)`. Long-
running gateways leaked memory and carried stale override state.

The fix exposes a generic callback hook on SessionRegistry so consumers
(PermissionSystem is the first, but future cleanups — transcript handles,
metric flushes — can hook in the same way).
"""
from __future__ import annotations

import pytest

from yigthinker.permissions import PermissionSystem
from yigthinker.presence.gateway.session_registry import SessionRegistry


def test_add_session_removed_callback_method_exists():
    """Contract: SessionRegistry must expose `add_session_removed_callback`."""
    registry = SessionRegistry()
    assert hasattr(registry, "add_session_removed_callback")
    assert callable(registry.add_session_removed_callback)


@pytest.mark.asyncio
async def test_callback_invoked_on_hibernate(tmp_path):
    """Hibernating a session must fire registered callbacks with its
    session_id — not the registry key."""
    registry = SessionRegistry(hibernate_dir=tmp_path)
    session = registry.get_or_create("test:user1", {}, "test")
    expected_session_id = session.ctx.session_id

    captured: list[str] = []
    registry.add_session_removed_callback(captured.append)

    ok = await registry.hibernate("test:user1")
    assert ok
    assert captured == [expected_session_id]


@pytest.mark.asyncio
async def test_callback_invoked_on_evict_idle(tmp_path):
    """Eviction goes through hibernate() so the callback must fire too."""
    registry = SessionRegistry(hibernate_dir=tmp_path, idle_timeout=0)
    session = registry.get_or_create("test:user1", {}, "test")
    expected_session_id = session.ctx.session_id
    session.last_active = session.last_active - 1.0  # force idle

    captured: list[str] = []
    registry.add_session_removed_callback(captured.append)

    count = await registry.evict_idle()
    assert count == 1
    assert captured == [expected_session_id]


@pytest.mark.asyncio
async def test_callback_invoked_on_shutdown(tmp_path):
    """Gateway shutdown hibernates every active session — callbacks fire
    once per session, with the right session_id."""
    registry = SessionRegistry(hibernate_dir=tmp_path)
    s1 = registry.get_or_create("test:user1", {}, "test")
    s2 = registry.get_or_create("test:user2", {}, "test")
    expected_ids = {s1.ctx.session_id, s2.ctx.session_id}

    captured: list[str] = []
    registry.add_session_removed_callback(captured.append)

    await registry.shutdown()
    assert set(captured) == expected_ids
    assert len(captured) == 2


@pytest.mark.asyncio
async def test_callback_failure_does_not_block_hibernation(tmp_path):
    """A misbehaving callback must not prevent session removal — the
    registry is authoritative on session lifecycle. Errors are logged
    and swallowed."""
    registry = SessionRegistry(hibernate_dir=tmp_path)
    registry.get_or_create("test:user1", {}, "test")

    def boom(_sid: str) -> None:
        raise RuntimeError("bad callback")

    registry.add_session_removed_callback(boom)

    ok = await registry.hibernate("test:user1")
    assert ok
    assert registry.active_count == 0  # session still removed


@pytest.mark.asyncio
async def test_multiple_callbacks_all_invoked(tmp_path):
    """All registered callbacks run for each removal."""
    registry = SessionRegistry(hibernate_dir=tmp_path)
    registry.get_or_create("test:user1", {}, "test")

    a: list[str] = []
    b: list[str] = []
    registry.add_session_removed_callback(a.append)
    registry.add_session_removed_callback(b.append)

    await registry.hibernate("test:user1")
    assert len(a) == 1
    assert len(b) == 1
    assert a == b


# ---------------------------------------------------------------------------
# Integration: PermissionSystem.clear_session wiring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_permission_overrides_cleared_on_hibernate(tmp_path):
    """End-to-end: register PermissionSystem.clear_session as the callback,
    grant an override, hibernate — the override must be gone from the
    PermissionSystem's internal state."""
    perms = PermissionSystem({"ask": ["*"]})
    registry = SessionRegistry(hibernate_dir=tmp_path)
    registry.add_session_removed_callback(perms.clear_session)

    session = registry.get_or_create("test:user1", {}, "test")
    sid = session.ctx.session_id
    perms.allow_for_session("workflow_deploy", sid)
    assert sid in perms._session_overrides  # pre-condition

    await registry.hibernate("test:user1")
    assert sid not in perms._session_overrides
