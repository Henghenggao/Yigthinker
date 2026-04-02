from typer.testing import CliRunner
from unittest.mock import patch
from yigthinker.__main__ import app

runner = CliRunner()


def test_dashboard_command_exists():
    result = runner.invoke(app, ["dashboard", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output
