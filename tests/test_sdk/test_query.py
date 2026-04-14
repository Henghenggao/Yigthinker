import pytest
from unittest.mock import AsyncMock, MagicMock, patch


async def test_query_returns_string():
    from yigthinker import sdk

    mock_loop = MagicMock()
    mock_loop.run = AsyncMock(return_value="result text")
    mock_app = MagicMock()
    mock_app.agent_loop = mock_loop

    with patch("yigthinker.sdk.build_app", return_value=mock_app) as mock_build, \
         patch("yigthinker.sdk.load_settings", return_value={}), \
         patch("yigthinker.sdk.SessionContext") as mock_ctx_cls:
        mock_ctx_cls.return_value = MagicMock(session_id="auto")
        result = await sdk.query("what is 2+2?")

    assert result == "result text"


async def test_create_session_returns_sdk_session():
    from yigthinker import sdk
    from yigthinker.sdk.session import SDKSession

    mock_app = MagicMock()
    mock_app.agent_loop = MagicMock()

    with patch("yigthinker.sdk.build_app", return_value=mock_app), \
         patch("yigthinker.sdk.load_settings", return_value={}), \
         patch("yigthinker.sdk.SessionContext") as mock_ctx_cls:
        mock_ctx_cls.return_value = MagicMock(session_id="new-session")
        session = await sdk.create_session()

    assert isinstance(session, SDKSession)


async def test_create_session_merges_settings_override():
    from yigthinker import sdk

    mock_app = MagicMock()
    mock_app.agent_loop = MagicMock()

    with patch("yigthinker.sdk.build_app", return_value=mock_app) as mock_build, \
         patch("yigthinker.sdk.load_settings", return_value={"model": "default-model"}), \
         patch("yigthinker.sdk.SessionContext") as mock_ctx_cls:
        mock_ctx_cls.return_value = MagicMock(session_id="s")
        await sdk.create_session(settings={"model": "claude-opus-4-6"})

    called_settings = mock_build.call_args[0][0]
    assert called_settings["model"] == "claude-opus-4-6"
