# tests/test_cli_main.py
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from yigthinker.__main__ import app

runner = CliRunner()


def test_single_query_mode():
    """yigthinker "some query" should call build_app and run the agent loop."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value="test output")
    mock_pool = MagicMock()

    mock_app_ctx = MagicMock()
    mock_app_ctx.agent_loop = mock_agent
    mock_app_ctx.pool = mock_pool

    with patch("yigthinker.builder.build_app", new_callable=AsyncMock, return_value=mock_app_ctx):
        result = runner.invoke(app, ["main", "hello world"])
    assert result.exit_code == 0
    mock_agent.run.assert_called_once()


def test_help_flag():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output
