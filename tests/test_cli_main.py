# tests/test_cli_main.py
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from yigthinker.__main__ import _normalize_cli_args, app, run

runner = CliRunner()


def test_single_query_mode():
    """yigthinker "some query" should call build_app and run the agent loop."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value="test output")
    mock_pool = MagicMock()

    mock_app_ctx = MagicMock()
    mock_app_ctx.agent_loop = mock_agent
    mock_app_ctx.pool = mock_pool

    with patch("yigthinker.settings.has_api_key", return_value=True), \
         patch("yigthinker.builder.build_app", new_callable=AsyncMock, return_value=mock_app_ctx):
        result = runner.invoke(app, ["main", "hello world"])
    assert result.exit_code == 0
    mock_agent.run.assert_called_once()


def test_help_flag():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_normalize_cli_args_routes_documented_root_modes():
    assert _normalize_cli_args([]) == ["main"]
    assert _normalize_cli_args(["hello world"]) == ["main", "hello world"]
    assert _normalize_cli_args(["--resume"]) == ["main", "--resume"]
    assert _normalize_cli_args(["setup"]) == ["setup"]
    assert _normalize_cli_args(["gateway"]) == ["gateway"]
    assert _normalize_cli_args(["--help"]) == ["--help"]


def test_run_dispatches_bare_query_to_default_main():
    captured = {}

    class DummyCommand:
        def main(self, *, args, prog_name):
            captured["args"] = args
            captured["prog_name"] = prog_name

    with patch("yigthinker.__main__.get_command", return_value=DummyCommand()):
        run(["hello world"])

    assert captured["args"] == ["main", "hello world"]
    assert captured["prog_name"] == "yigthinker"


def test_setup_command_invokes_setup_wizard():
    with patch("yigthinker.cli.setup_wizard.run_setup") as mock_run_setup:
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    mock_run_setup.assert_called_once_with()
