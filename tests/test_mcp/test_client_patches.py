"""Phase 1b MCP client patches — reconnect, parallel discovery, stable sort, token helper."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from yigthinker.mcp.client import MCPClient, MCPToolDef
from yigthinker.mcp.loader import MCPLoader
from yigthinker.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 1. auto_reconnect_on_tool_exec_failure
# ---------------------------------------------------------------------------

async def test_call_tool_auto_reconnects_once_on_error():
    """First call_tool raises; client stops+starts a fresh session; retry succeeds."""
    client = MCPClient(name="test", transport="stdio", command="echo")

    restart_count = {"n": 0}

    async def fake_stop():
        client._session = None  # mirror real stop() behavior

    async def fake_start():
        restart_count["n"] += 1
        # Install a fresh session whose call_tool succeeds.
        fresh_session = MagicMock()
        async def ok_call_tool(*a, **kw):
            class R:
                content = [type("Block", (), {"text": "ok"})()]
            return R()
        fresh_session.call_tool = ok_call_tool
        client._session = fresh_session

    client.stop = fake_stop  # type: ignore[method-assign]
    client.start = fake_start  # type: ignore[method-assign]

    # Initial session fails once
    initial_session = MagicMock()
    async def first_call_fails(*a, **kw):
        raise RuntimeError("connection lost")
    initial_session.call_tool = first_call_fails
    client._session = initial_session

    result = await client.call_tool("some_tool", {})
    assert result == "ok"
    assert restart_count["n"] == 1
    # After reconnect, the session should be the fresh one, not the initial one.
    assert client._session is not initial_session


async def test_call_tool_raises_when_start_does_not_restore_session():
    """If start() returns without setting _session, retry aborts with RuntimeError."""
    client = MCPClient(name="test", transport="stdio", command="echo")

    async def fake_stop():
        client._session = None

    async def fake_start_bad():
        pass  # bug: doesn't restore _session

    client.stop = fake_stop  # type: ignore[method-assign]
    client.start = fake_start_bad  # type: ignore[method-assign]

    initial_session = MagicMock()
    async def fail(*a, **kw):
        raise RuntimeError("initial failure")
    initial_session.call_tool = fail
    client._session = initial_session

    with pytest.raises(RuntimeError, match="failed to reconnect"):
        await client.call_tool("some_tool", {})


async def test_call_tool_second_failure_raises():
    """If both attempts fail, error propagates."""
    client = MCPClient(name="test", transport="stdio", command="echo")

    async def fake_stop():
        pass

    async def fake_start():
        pass

    async def always_fails(*a, **kw):
        raise RuntimeError("permanent")

    client.stop = fake_stop  # type: ignore[method-assign]
    client.start = fake_start  # type: ignore[method-assign]
    client._session = MagicMock()
    client._session.call_tool = always_fails

    with pytest.raises(RuntimeError, match="permanent"):
        await client.call_tool("some_tool", {})


# ---------------------------------------------------------------------------
# 2. parallel_tool_discovery
# ---------------------------------------------------------------------------

async def test_loader_starts_clients_in_parallel(tmp_path):
    """MCPLoader.load calls client.start() concurrently — at least 2 run in parallel."""
    import json

    cfg = {"mcpServers": {
        f"s{i}": {"command": "echo", "args": [str(i)]} for i in range(3)
    }}
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps(cfg))

    registry = ToolRegistry()
    loader = MCPLoader(mcp_json, registry)

    from yigthinker.mcp import loader as loader_mod
    original = loader_mod.MCPClient

    in_flight = {"current": 0, "peak": 0}

    class SlowClient:
        def __init__(self, **kw):
            self.name = kw["name"]

        async def start(self):
            in_flight["current"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
            await asyncio.sleep(0.05)
            in_flight["current"] -= 1

        async def stop(self):
            pass

        async def list_tools(self):
            return []

        async def list_resources(self):
            return []

    loader_mod.MCPClient = SlowClient  # type: ignore[misc]
    try:
        await loader.load()
    finally:
        loader_mod.MCPClient = original

    # At least 2 clients must have been in-flight simultaneously for the
    # gather to be meaningfully parallel (3 is the ideal for 3 servers).
    assert in_flight["peak"] >= 2, f"Expected >=2 concurrent starts; peak was {in_flight['peak']}"


# ---------------------------------------------------------------------------
# 3. stable_tool_name_sort
# ---------------------------------------------------------------------------

async def test_loader_registers_tools_in_sorted_order(tmp_path):
    import json

    cfg = {"mcpServers": {"srv": {"command": "echo"}}}
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps(cfg))

    registry = ToolRegistry()
    loader = MCPLoader(mcp_json, registry)

    from yigthinker.mcp import loader as loader_mod
    original = loader_mod.MCPClient

    class FakeClient:
        def __init__(self, **kw): pass
        async def start(self): pass
        async def stop(self): pass
        async def list_tools(self):
            return [
                MCPToolDef(name="zulu", description="", input_schema={}),
                MCPToolDef(name="alpha", description="", input_schema={}),
                MCPToolDef(name="mike", description="", input_schema={}),
            ]
        async def list_resources(self):
            return []

    loader_mod.MCPClient = FakeClient  # type: ignore[misc]
    try:
        await loader.load()
    finally:
        loader_mod.MCPClient = original

    names = registry.names()
    # All 3 should be present, and the registration order should be alphabetical
    idxs = {n: i for i, n in enumerate(names)}
    assert idxs["alpha"] < idxs["mike"] < idxs["zulu"]


# ---------------------------------------------------------------------------
# 4. bearer_token_constant_time_compare
# ---------------------------------------------------------------------------

def test_constant_time_equal_helper_exists_and_works():
    from yigthinker.mcp.client import constant_time_equal
    assert constant_time_equal("secret", "secret") is True
    assert constant_time_equal("secret", "secreT") is False
    assert constant_time_equal("", "") is True
    # Different lengths
    assert constant_time_equal("a", "ab") is False


def test_constant_time_equal_rejects_non_strings():
    from yigthinker.mcp.client import constant_time_equal
    with pytest.raises((TypeError, AttributeError)):
        constant_time_equal(None, "x")  # type: ignore[arg-type]
