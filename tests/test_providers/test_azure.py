from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.providers.azure import AzureProvider
from yigthinker.types import Message


def _make_openai_response(content="Hello", tool_calls=None):
    """Build a mock OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


async def test_azure_chat_end_turn():
    with patch("yigthinker.providers.azure.openai.AsyncAzureOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("Azure says hello")
        )
        provider = AzureProvider(
            deployment_name="gpt-4o",
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com/",
        )
        result = await provider.chat(
            [Message(role="user", content="Hello")], tools=[]
        )

    assert result.stop_reason == "end_turn"
    assert result.text == "Azure says hello"


async def test_azure_chat_with_tool_use():
    tool_call = MagicMock()
    tool_call.id = "call_abc123"
    tool_call.function.name = "echo"
    tool_call.function.arguments = '{"message": "hi"}'

    with patch("yigthinker.providers.azure.openai.AsyncAzureOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response(content=None, tool_calls=[tool_call])
        )
        provider = AzureProvider(
            deployment_name="gpt-4o",
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com/",
        )
        result = await provider.chat(
            [Message(role="user", content="echo hi")], tools=[]
        )

    assert result.stop_reason == "tool_use"
    assert len(result.tool_uses) == 1
    assert result.tool_uses[0].name == "echo"
