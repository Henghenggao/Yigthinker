from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
from yigthinker.advisor.advisor import AdvisorHook, AdvisorConfig
from yigthinker.types import HookEvent, HookAction


def _make_event(tool_name: str, tool_input: dict) -> HookEvent:
    return HookEvent(
        event_type="PreToolUse",
        session_id="test-session",
        transcript_path=None,
        tool_name=tool_name,
        tool_input=tool_input,
    )


async def test_advisor_disabled_allows_all():
    config = AdvisorConfig(enabled=False)
    hook = AdvisorHook(config=config, provider=None)
    event = _make_event("sql_query", {"query": "SELECT * FROM orders"})
    result = await hook.run(event)
    assert result.action == HookAction.ALLOW


async def test_advisor_approves_valid_call():
    config = AdvisorConfig(enabled=True)
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(return_value=MagicMock(text="APPROVE", tool_uses=[]))
    hook = AdvisorHook(config=config, provider=mock_provider)
    event = _make_event("sql_query", {"query": "SELECT * FROM orders WHERE region = 'East'"})
    result = await hook.run(event)
    assert result.action == HookAction.ALLOW


async def test_advisor_blocks_invalid_call():
    config = AdvisorConfig(enabled=True)
    mock_provider = AsyncMock()
    mock_provider.chat = AsyncMock(
        return_value=MagicMock(
            text="BLOCK: Mixing AR and AP in a direct JOIN is semantically incorrect.",
            tool_uses=[]
        )
    )
    hook = AdvisorHook(config=config, provider=mock_provider)
    event = _make_event("sql_query", {"query": "SELECT * FROM ar JOIN ap ON ar.id = ap.id"})
    result = await hook.run(event)
    assert result.action == HookAction.BLOCK
    assert "AR" in result.message or "semantically" in result.message


async def test_advisor_only_fires_on_matched_tools():
    config = AdvisorConfig(enabled=True, matcher=r"sql_query|df_transform")
    mock_provider = AsyncMock()
    hook = AdvisorHook(config=config, provider=mock_provider)
    # chart_create should NOT trigger advisor
    event = _make_event("chart_create", {"chart_type": "bar"})
    result = await hook.run(event)
    assert result.action == HookAction.ALLOW
    mock_provider.chat.assert_not_called()


async def test_advisor_does_not_match_partial_tool_name():
    config = AdvisorConfig(enabled=True, matcher=r"sql_query|df_transform")
    mock_provider = AsyncMock()
    hook = AdvisorHook(config=config, provider=mock_provider)
    # sql_query_extended should NOT match sql_query
    event = _make_event("sql_query_extended", {"query": "SELECT 1"})
    result = await hook.run(event)
    assert result.action == HookAction.ALLOW
    mock_provider.chat.assert_not_called()
