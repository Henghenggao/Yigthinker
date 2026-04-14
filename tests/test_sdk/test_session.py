import pytest
from unittest.mock import AsyncMock, MagicMock
from yigthinker.sdk.session import SDKSession


async def test_sdk_session_message_returns_text():
    mock_loop = MagicMock()
    mock_loop.run = AsyncMock(return_value="analysis complete")
    mock_ctx = MagicMock()
    mock_ctx.session_id = "sdk-session-1"

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    result = await session.message("analyze data")

    assert result == "analysis complete"
    mock_loop.run.assert_called_once_with("analyze data", mock_ctx)


async def test_sdk_session_preserves_session_id():
    mock_loop = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.session_id = "my-session-42"

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    assert session.session_id == "my-session-42"


async def test_sdk_session_on_token_callback():
    tokens_received: list[str] = []
    mock_loop = MagicMock()
    mock_loop.run = AsyncMock(return_value="done")
    mock_ctx = MagicMock()
    mock_ctx.session_id = "s1"

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    await session.message("go", on_token=tokens_received.append)

    mock_loop.run.assert_called_once_with("go", mock_ctx, on_token=tokens_received.append)


async def test_sdk_session_list_vars_delegates_to_ctx():
    mock_loop = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.session_id = "s1"
    mock_ctx.vars.list.return_value = [MagicMock(name="df1")]

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    vars_list = session.list_vars()

    assert len(vars_list) == 1
    mock_ctx.vars.list.assert_called_once()


async def test_sdk_session_checkpoint_delegates_to_ctx():
    mock_loop = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.session_id = "s1"

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    session.checkpoint("my_label")

    mock_ctx.checkpoint.assert_called_once_with("my_label")


async def test_sdk_session_branch_from_returns_new_sdk_session():
    mock_loop = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.session_id = "s1"
    new_ctx = MagicMock()
    new_ctx.session_id = "s2"
    mock_ctx.branch_from.return_value = new_ctx

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    branched = session.branch_from("my_label")

    mock_ctx.branch_from.assert_called_once_with("my_label")
    assert isinstance(branched, SDKSession)
    assert branched.session_id == "s2"


async def test_sdk_session_branch_returns_new_sdk_session():
    mock_loop = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.session_id = "s1"
    new_ctx = MagicMock()
    new_ctx.session_id = "s3"
    mock_ctx.branch.return_value = new_ctx

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    branched = session.branch()

    mock_ctx.branch.assert_called_once()
    assert isinstance(branched, SDKSession)
    assert branched.session_id == "s3"


async def test_sdk_session_list_checkpoints_delegates_to_ctx():
    mock_loop = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.session_id = "s1"
    mock_ctx.list_checkpoints.return_value = ["cp1", "cp2"]

    session = SDKSession(agent_loop=mock_loop, ctx=mock_ctx)
    labels = session.list_checkpoints()

    mock_ctx.list_checkpoints.assert_called_once()
    assert labels == ["cp1", "cp2"]
