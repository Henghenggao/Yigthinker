import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from yigthinker.types import Message, LLMResponse, ThinkingConfig
from yigthinker.providers.claude import ClaudeProvider


def make_mock_anthropic_response(
    stop_reason: str = "end_turn",
    text: str = "Hello",
    tool_uses: list | None = None,
):
    content = []
    if text:
        block = MagicMock()
        block.type = "text"
        block.text = text
        content.append(block)
    for tu in (tool_uses or []):
        block = MagicMock()
        block.type = "tool_use"
        block.id = tu["id"]
        block.name = tu["name"]
        block.input = tu["input"]
        content.append(block)
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content
    return response


async def test_chat_end_turn(monkeypatch):
    mock_response = make_mock_anthropic_response(stop_reason="end_turn", text="Result")

    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = ClaudeProvider(model="claude-sonnet-4-20250514", api_key="test")
        messages = [Message(role="user", content="Hello")]
        result = await provider.chat(messages, tools=[])

    assert result.stop_reason == "end_turn"
    assert result.text == "Result"
    assert result.tool_uses == []


async def test_chat_tool_use(monkeypatch):
    mock_response = make_mock_anthropic_response(
        stop_reason="tool_use",
        text="",
        tool_uses=[{"id": "tu1", "name": "echo", "input": {"message": "hi"}}],
    )

    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = ClaudeProvider(model="claude-sonnet-4-20250514", api_key="test")
        messages = [Message(role="user", content="echo hi")]
        result = await provider.chat(messages, tools=[])

    assert result.stop_reason == "tool_use"
    assert len(result.tool_uses) == 1
    assert result.tool_uses[0].name == "echo"
    assert result.tool_uses[0].input == {"message": "hi"}


async def test_chat_passes_thinking_param_when_enabled():
    mock_response = make_mock_anthropic_response(stop_reason="end_turn", text="Deep thought")
    # Add a thinking block to the mock response content
    thinking_block = MagicMock()
    thinking_block.type = "thinking"
    thinking_block.thinking = "I reasoned carefully"
    mock_response.content.insert(0, thinking_block)

    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = ClaudeProvider(
            model="claude-opus-4-6",
            api_key="test",
            thinking=ThinkingConfig(enabled=True, budget_tokens=5000),
        )
        messages = [Message(role="user", content="Think deeply")]
        result = await provider.chat(messages, tools=[])

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["thinking"] == {"type": "enabled", "budget_tokens": 5000}
    assert result.thinking_blocks == [{"type": "thinking", "thinking": "I reasoned carefully"}]


async def test_chat_no_thinking_param_when_disabled():
    mock_response = make_mock_anthropic_response(stop_reason="end_turn", text="Normal")

    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = ClaudeProvider(model="claude-opus-4-6", api_key="test")
        result = await provider.chat([Message(role="user", content="Hi")], tools=[])

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "thinking" not in call_kwargs
    assert result.thinking_blocks == []
