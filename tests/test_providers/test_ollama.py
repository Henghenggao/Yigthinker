from unittest.mock import AsyncMock, patch

from yigthinker.providers.ollama import OllamaProvider
from yigthinker.types import Message


async def test_chat_end_turn():
    mock_response = {
        "message": {"role": "assistant", "content": "Result", "tool_calls": None},
        "done": True,
    }

    with patch("yigthinker.providers.ollama._http_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        provider = OllamaProvider(model="llama3", base_url="http://localhost:11434")
        result = await provider.chat([Message(role="user", content="Hello")], tools=[])

    assert result.stop_reason == "end_turn"
    assert result.text == "Result"


async def test_chat_with_tool_call():
    mock_response = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "echo", "arguments": {"message": "hello"}}}
            ],
        },
        "done": True,
    }

    with patch("yigthinker.providers.ollama._http_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        provider = OllamaProvider(model="llama3", base_url="http://localhost:11434")
        result = await provider.chat([Message(role="user", content="echo hello")], tools=[])

    assert result.stop_reason == "tool_use"
    assert result.tool_uses[0].name == "echo"
