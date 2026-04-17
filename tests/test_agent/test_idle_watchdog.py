"""Idle watchdog — stream that goes silent for N seconds is aborted + retried once."""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import LLMResponse, StreamEvent


class _HangingStream:
    """Yields one text event then sleeps forever — triggers the idle watchdog."""

    def __init__(self) -> None:
        self.aborted = False

    async def __aiter__(self):
        yield StreamEvent(type="text", text="partial...")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.aborted = True
            raise


class _NormalStream:
    """Yields 'ok' + done quickly."""

    async def __aiter__(self):
        yield StreamEvent(type="text", text="ok")
        yield StreamEvent(type="done", stop_reason="end_turn")


async def test_idle_watchdog_aborts_and_retries():
    hanging = _HangingStream()
    normal = _NormalStream()
    stream_returns = iter([hanging, normal])

    mock_provider = AsyncMock()
    mock_provider.stream = lambda *a, **kw: next(stream_returns)
    mock_provider.chat = AsyncMock(return_value=LLMResponse(stop_reason="end_turn", text="ok"))

    tools = ToolRegistry()
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["*"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    loop._stream_idle_timeout_seconds = 0.2  # type: ignore[attr-defined]

    result = await asyncio.wait_for(
        loop.run("hello", SessionContext(), on_token=lambda _t: None),
        timeout=5.0,
    )

    assert hanging.aborted, "First stream should have been cancelled by watchdog"
    assert result == "ok"


async def test_idle_watchdog_gives_up_after_second_timeout():
    stream_returns = iter([_HangingStream(), _HangingStream()])

    mock_provider = AsyncMock()
    mock_provider.stream = lambda *a, **kw: next(stream_returns)
    mock_provider.chat = AsyncMock()

    tools = ToolRegistry()
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["*"]})
    loop = AgentLoop(provider=mock_provider, tools=tools, hooks=hooks, permissions=perms)
    loop._stream_idle_timeout_seconds = 0.2  # type: ignore[attr-defined]

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            loop.run("hello", SessionContext(), on_token=lambda _t: None),
            timeout=5.0,
        )
