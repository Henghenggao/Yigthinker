"""H4 (Phase 1a housekeeping): definitional questions must get direct replies.

Complement of the Phase 0 action-first contract. Without this test, a
future edit tightening action-first could regress the "what is X" path
into always calling a tool when none is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import LLMResponse


def _mock_provider_that_returns_text(text: str):
    """Provider whose chat() always returns plain assistant text (no tool_use)."""
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=LLMResponse(
            stop_reason="end_turn",
            text=text,
            tool_uses=[],
        )
    )
    return provider


@pytest.mark.asyncio
async def test_definitional_question_returns_direct_text(default_settings):
    """'What is EBITDA?' must resolve via direct text reply, no tool_call."""
    ctx = SessionContext(settings=default_settings)

    provider = _mock_provider_that_returns_text(
        "EBITDA stands for Earnings Before Interest, Taxes, Depreciation and Amortization..."
    )
    loop = AgentLoop(
        provider=provider,
        tools=ToolRegistry(),
        hooks=HookExecutor(HookRegistry()),
        permissions=PermissionSystem({}),
    )

    result = await loop.run("What is EBITDA?", ctx)

    # (1) Provider called exactly once — no tool-call round trips.
    assert provider.chat.await_count == 1

    # (2) Final reply text contains the definitional answer.
    assert "EBITDA" in result

    # (3) VarRegistry is empty — no artifacts were registered.
    assert ctx.vars.list() == []
