# tests/test_providers/test_streaming.py
# Tests for streaming (stream()) on all 4 LLM providers.
import json

from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.types import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(async_gen):
    """Collect all items from an async generator into a list."""
    items = []
    async for item in async_gen:
        items.append(item)
    return items


class _FakeAnthropicStreamCtx:
    """Fake async context manager mimicking the Anthropic SDK stream()."""

    def __init__(self, events, final_message):
        self._events = events
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def __aiter__(self):
        for e in self._events:
            yield e

    async def get_final_message(self):
        return self._final_message


# ---------------------------------------------------------------------------
# Claude Provider Tests
# ---------------------------------------------------------------------------

async def test_claude_stream_text():
    """ClaudeProvider.stream() yields text events and a done event."""
    text_event = MagicMock()
    text_event.type = "text"
    text_event.text = "Hello world"

    final_msg = MagicMock()
    final_msg.stop_reason = "end_turn"

    stream_ctx = _FakeAnthropicStreamCtx([text_event], final_msg)

    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=stream_ctx)
        mock_client.messages.create = AsyncMock()

        from yigthinker.providers.claude import ClaudeProvider
        provider = ClaudeProvider(model="claude-sonnet-4-20250514", api_key="test")
        events = await _collect(provider.stream([Message(role="user", content="Hi")], tools=[]))

    text_events = [e for e in events if e.type == "text"]
    done_events = [e for e in events if e.type == "done"]
    assert len(text_events) >= 1
    assert text_events[0].text == "Hello world"
    assert len(done_events) == 1
    assert done_events[0].stop_reason == "end_turn"


async def test_claude_stream_tool_use():
    """ClaudeProvider.stream() yields tool_use events from content_block_stop."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu1"
    tool_block.name = "echo"
    tool_block.input = {"message": "hi"}

    block_stop_event = MagicMock()
    block_stop_event.type = "content_block_stop"
    block_stop_event.content_block = tool_block

    final_msg = MagicMock()
    final_msg.stop_reason = "tool_use"

    stream_ctx = _FakeAnthropicStreamCtx([block_stop_event], final_msg)

    with patch("yigthinker.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=stream_ctx)
        mock_client.messages.create = AsyncMock()

        from yigthinker.providers.claude import ClaudeProvider
        provider = ClaudeProvider(model="claude-sonnet-4-20250514", api_key="test")
        events = await _collect(provider.stream([Message(role="user", content="echo hi")], tools=[]))

    tool_events = [e for e in events if e.type == "tool_use"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_use is not None
    assert tool_events[0].tool_use.name == "echo"
    assert tool_events[0].tool_use.input == {"message": "hi"}


# ---------------------------------------------------------------------------
# OpenAI Provider Tests
# ---------------------------------------------------------------------------

async def test_openai_stream_text():
    """OpenAIProvider.stream() yields text events from delta.content chunks."""

    def make_chunk(content=None, finish_reason=None, tool_calls=None):
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = tool_calls
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish_reason
        chunk = MagicMock()
        chunk.choices = [choice]
        return chunk

    async def mock_stream():
        yield make_chunk(content="Hello")
        yield make_chunk(content=" world")
        yield make_chunk(finish_reason="stop")

    with patch("yigthinker.providers.openai.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        from yigthinker.providers.openai import OpenAIProvider
        provider = OpenAIProvider(model="gpt-4o", api_key="test")
        events = await _collect(provider.stream([Message(role="user", content="Hi")], tools=[]))

    text_events = [e for e in events if e.type == "text"]
    done_events = [e for e in events if e.type == "done"]
    assert len(text_events) == 2
    assert text_events[0].text == "Hello"
    assert text_events[1].text == " world"
    assert len(done_events) == 1
    assert done_events[0].stop_reason == "end_turn"


async def test_openai_stream_tool_calls():
    """OpenAIProvider.stream() accumulates tool_call deltas and yields tool_use events."""

    def make_chunk(content=None, finish_reason=None, tool_calls=None):
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = tool_calls
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish_reason
        chunk = MagicMock()
        chunk.choices = [choice]
        return chunk

    def make_tool_call_delta(index, id=None, name=None, arguments=None):
        tc = MagicMock()
        tc.index = index
        tc.id = id
        tc.function = MagicMock()
        tc.function.name = name
        tc.function.arguments = arguments
        return tc

    async def mock_stream():
        # First chunk: tool call start with id and name
        yield make_chunk(tool_calls=[make_tool_call_delta(0, id="tc1", name="echo", arguments='{"mes')])
        # Second chunk: continuation of arguments
        yield make_chunk(tool_calls=[make_tool_call_delta(0, arguments='sage": "hi"}')])
        # Finish
        yield make_chunk(finish_reason="tool_calls")

    with patch("yigthinker.providers.openai.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        from yigthinker.providers.openai import OpenAIProvider
        provider = OpenAIProvider(model="gpt-4o", api_key="test")
        events = await _collect(provider.stream([Message(role="user", content="echo hi")], tools=[]))

    tool_events = [e for e in events if e.type == "tool_use"]
    done_events = [e for e in events if e.type == "done"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_use is not None
    assert tool_events[0].tool_use.id == "tc1"
    assert tool_events[0].tool_use.name == "echo"
    assert tool_events[0].tool_use.input == {"message": "hi"}
    assert len(done_events) == 1
    assert done_events[0].stop_reason == "tool_use"


# ---------------------------------------------------------------------------
# Ollama Provider Tests
# ---------------------------------------------------------------------------

async def test_ollama_stream_text():
    """OllamaProvider.stream() yields text events from NDJSON lines."""
    ndjson_lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": " world"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    async def mock_aiter_lines():
        for line in ndjson_lines:
            yield line

    mock_response = AsyncMock()
    mock_response.aiter_lines = mock_aiter_lines

    # Build the nested context managers
    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = AsyncMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("yigthinker.providers.ollama.httpx.AsyncClient", return_value=mock_client_ctx):
        from yigthinker.providers.ollama import OllamaProvider
        provider = OllamaProvider(model="llama3", base_url="http://localhost:11434")
        events = await _collect(provider.stream([Message(role="user", content="Hi")], tools=[]))

    text_events = [e for e in events if e.type == "text"]
    done_events = [e for e in events if e.type == "done"]
    assert len(text_events) == 2
    assert text_events[0].text == "Hello"
    assert text_events[1].text == " world"
    assert len(done_events) == 1
    assert done_events[0].stop_reason == "end_turn"


async def test_ollama_stream_tool_calls():
    """OllamaProvider.stream() yields tool_use events from NDJSON with tool_calls."""
    ndjson_lines = [
        json.dumps({
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "echo", "arguments": {"message": "hi"}}}
                ],
            },
            "done": True,
        }),
    ]

    async def mock_aiter_lines():
        for line in ndjson_lines:
            yield line

    mock_response = AsyncMock()
    mock_response.aiter_lines = mock_aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = AsyncMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("yigthinker.providers.ollama.httpx.AsyncClient", return_value=mock_client_ctx):
        from yigthinker.providers.ollama import OllamaProvider
        provider = OllamaProvider(model="llama3", base_url="http://localhost:11434")
        events = await _collect(provider.stream([Message(role="user", content="echo hi")], tools=[]))

    tool_events = [e for e in events if e.type == "tool_use"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_use is not None
    assert tool_events[0].tool_use.name == "echo"
    assert tool_events[0].tool_use.input == {"message": "hi"}


# ---------------------------------------------------------------------------
# Azure Provider Tests
# ---------------------------------------------------------------------------

async def test_azure_stream_inherits_openai():
    """AzureProvider inherits stream() from OpenAIProvider."""
    with patch("yigthinker.providers.azure.openai.AsyncAzureOpenAI"):
        from yigthinker.providers.azure import AzureProvider
        provider = AzureProvider(
            deployment_name="gpt-4o",
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com",
        )
        assert hasattr(provider, "stream")
        assert callable(provider.stream)
