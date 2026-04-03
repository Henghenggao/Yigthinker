"""Tests for session registry lifecycle."""
import asyncio

import pandas as pd
import pytest

from yigthinker.gateway.session_registry import ManagedSession, SessionRegistry


def test_get_or_create_new():
    registry = SessionRegistry(max_sessions=10)
    session = registry.get_or_create("test:user1", {}, "test")
    assert session.key == "test:user1"
    assert session.channel_origin == "test"
    assert registry.active_count == 1


def test_get_or_create_existing():
    registry = SessionRegistry()
    s1 = registry.get_or_create("test:user1", {}, "test")
    s2 = registry.get_or_create("test:user1", {}, "test")
    assert s1 is s2
    assert registry.active_count == 1


def test_remove():
    registry = SessionRegistry()
    registry.get_or_create("test:user1", {}, "test")
    removed = registry.remove("test:user1")
    assert removed is not None
    assert registry.active_count == 0


def test_remove_nonexistent():
    registry = SessionRegistry()
    assert registry.remove("nope") is None


def test_list_sessions():
    registry = SessionRegistry()
    registry.get_or_create("test:user1", {}, "test")
    registry.get_or_create("test:user2", {}, "test")
    sessions = registry.list_sessions()
    assert len(sessions) == 2
    keys = {s["key"] for s in sessions}
    assert keys == {"test:user1", "test:user2"}


def test_lru_eviction():
    registry = SessionRegistry(max_sessions=2)
    s1 = registry.get_or_create("test:a", {}, "test")
    s2 = registry.get_or_create("test:b", {}, "test")

    # Touch s2 to make s1 the LRU
    s2.touch()

    # Creating a third should evict s1
    s3 = registry.get_or_create("test:c", {}, "test")
    assert registry.active_count == 2
    assert registry.get("test:a") is None
    assert registry.get("test:b") is not None
    assert registry.get("test:c") is not None


def test_session_to_info():
    registry = SessionRegistry()
    session = registry.get_or_create("test:user1", {}, "feishu")

    # Add a DataFrame variable
    session.ctx.vars.set("revenue", pd.DataFrame({"a": [1, 2, 3]}))

    info = session.to_info()
    assert info["key"] == "test:user1"
    assert info["channel_origin"] == "feishu"
    assert info["var_count"] == 1
    assert info["vars"][0]["name"] == "revenue"


@pytest.mark.asyncio
async def test_evict_idle():
    registry = SessionRegistry(idle_timeout=0)  # 0 = evict immediately
    session = registry.get_or_create("test:user1", {}, "test")
    # Force the session to appear idle by back-dating last_active
    session.last_active = session.last_active - 1.0
    count = await registry.evict_idle()
    assert count == 1
    assert registry.active_count == 0
