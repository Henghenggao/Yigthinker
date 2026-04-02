from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.providers.openai import OpenAIProvider
from yigthinker.types import Message


def make_openai_response(content: str = "Hello", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


async def test_chat_end_turn():
    with patch("yigthinker.providers.openai.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_openai_response("Answer")
        )

        provider = OpenAIProvider(model="gpt-4o", api_key="test")
        result = await provider.chat([Message(role="user", content="Hello")], tools=[])

    assert result.stop_reason == "end_turn"
    assert result.text == "Answer"
    assert result.tool_uses == []


async def test_chat_tool_call():
    tool_call = MagicMock()
    tool_call.id = "tc1"
    tool_call.function.name = "echo"
    tool_call.function.arguments = '{"message": "hi"}'

    with patch("yigthinker.providers.openai.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_openai_response("", [tool_call])
        )

        provider = OpenAIProvider(model="gpt-4o", api_key="test")
        result = await provider.chat([Message(role="user", content="echo hi")], tools=[])

    assert result.stop_reason == "tool_use"
    assert len(result.tool_uses) == 1
    assert result.tool_uses[0].name == "echo"
    assert result.tool_uses[0].input == {"message": "hi"}
