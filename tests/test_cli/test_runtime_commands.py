from typer.testing import CliRunner
from unittest.mock import MagicMock, patch

from yigthinker.__main__ import app

runner = CliRunner()


def test_gateway_command_prefers_cli_host_and_port():
    settings = {"gateway": {"host": "127.0.0.1", "port": 8766}, "channels": {}}

    with patch("yigthinker.settings.load_settings", return_value=settings), \
         patch("yigthinker.presence.gateway.server.GatewayServer", return_value=MagicMock()) as mock_gateway_server, \
         patch("uvicorn.run") as mock_uvicorn_run:
        result = runner.invoke(app, ["gateway", "--host", "0.0.0.0", "--port", "9000"])

    assert result.exit_code == 0
    mock_gateway_server.assert_called_once()
    mock_uvicorn_run.assert_called_once()
    _, kwargs = mock_uvicorn_run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9000
    assert settings["gateway"]["host"] == "0.0.0.0"
    assert settings["gateway"]["port"] == 9000
    assert "dashboard_url" not in settings

