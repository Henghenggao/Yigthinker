import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from yigthinker.types import Message, LLMResponse
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
