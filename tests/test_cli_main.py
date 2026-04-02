# tests/test_cli.py
from typer.testing import CliRunner
from unittest.mock import patch
from yigthinker.__main__ import app

runner = CliRunner()


def test_single_query_mode():
    """yigthinker "some query" should call the agent loop and print the result."""
    with patch("yigthinker.__main__._run_query", return_value="test output") as mock_run:
        result = runner.invoke(app, ["main", "hello world"])
    assert result.exit_code == 0
    mock_run.assert_called_once()


def test_help_flag():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output
