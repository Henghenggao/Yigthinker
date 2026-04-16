"""Verify the base system prompt is always injected into the agent loop."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import LLMResponse


@pytest.mark.asyncio
async def test_base_prompt_is_prepended_to_system(tmp_path):
    """The agent's first LLM call must include BASE_SYSTEM_PROMPT in `system=`."""
    # Mock LLM that captures the system prompt it receives
    captured_system: list[str | None] = []

    async def fake_chat(messages, tools, system=None):
        captured_system.append(system)
        return LLMResponse(stop_reason="end_turn", text="done", tool_uses=[])

    mock_provider = MagicMock()
    mock_provider.chat = fake_chat
    # Force non-streaming path: AgentLoop falls back to chat() when
    # stream() is not available or raises.
    mock_provider.supports_streaming = MagicMock(return_value=False)

    # Empty registry (no tools needed for this minimal assertion)
    registry = ToolRegistry()
    hooks_registry = HookRegistry()
    permissions = PermissionSystem({})
    executor = HookExecutor(hooks_registry)

    loop = AgentLoop(
        provider=mock_provider,
        tools=registry,
        hooks=executor,
        permissions=permissions,
    )

    ctx = SessionContext(
        session_id="test-session",
        settings={},
        transcript_path=str(tmp_path / "transcript.jsonl"),
    )

    await loop.run("hello", ctx)

    assert captured_system, "LLM provider was not called"
    first_system = captured_system[0] or ""
    base_signature = "You are Yigcore, an AI finance agent"
    assert base_signature in first_system, (
        f"Base system prompt was not injected. Got system starting with: "
        f"{first_system[:200]!r}"
    )
