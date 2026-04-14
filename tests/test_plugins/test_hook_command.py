import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from yigthinker.plugins.hook_command import CommandHook
from yigthinker.types import HookEvent, HookAction


def make_event() -> HookEvent:
    return HookEvent(
        event_type="PreToolUse",
        session_id="s1",
        transcript_path="",
        tool_name="sql_query",
        tool_input={"query": "SELECT 1"},
    )


async def test_command_hook_exit_0_returns_allow():
    hook = CommandHook(command="echo ok")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await hook(make_event())

    assert result.action == HookAction.ALLOW


async def test_command_hook_exit_1_returns_warn():
    hook = CommandHook(command="exit 1")
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"rate limit warning"))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await hook(make_event())

    assert result.action == HookAction.WARN
    assert "rate limit warning" in result.message


async def test_command_hook_exit_2_returns_block():
    hook = CommandHook(command="exit 2")
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.communicate = AsyncMock(return_value=(b"", b"blocked: PII detected"))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await hook(make_event())

    assert result.action == HookAction.BLOCK
    assert "PII detected" in result.message


async def test_command_hook_passes_event_as_json_on_stdin():
    hook = CommandHook(command="cat")
    received_input: list = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0

    async def mock_communicate(input=None):
        received_input.append(input)
        return (b"", b"")

    mock_proc.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        await hook(make_event())

    assert received_input[0] is not None
    payload = json.loads(received_input[0])
    assert payload["event_type"] == "PreToolUse"
    assert payload["tool_name"] == "sql_query"


async def test_command_hook_exception_returns_warn():
    """A crashing hook command should not block execution — returns WARN."""
    hook = CommandHook(command="nonexistent-command")

    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("no such file")):
        result = await hook(make_event())

    assert result.action == HookAction.WARN
    assert "Plugin hook error" in result.message
