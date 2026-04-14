import json
from unittest.mock import AsyncMock, patch

import pytest

from yigthinker.mcp.client import MCPToolDef
from yigthinker.mcp.loader import MCPLoader
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry


@pytest.fixture
def mcp_json(tmp_path):
    config = {
        "mcpServers": {
            "wind": {
                "command": "echo",
                "args": ["--api-key-env", "WIND_API_KEY"],
            }
        }
    }
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps(config))
    return path


async def test_loader_registers_mcp_tools(mcp_json):
    mock_client = AsyncMock()
    mock_client.list_tools = AsyncMock(
        return_value=[
            MCPToolDef(
                name="get_stock_price",
                description="Get stock price",
                input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}},
            )
        ]
    )
    mock_client.call_tool = AsyncMock(return_value='{"price": 100.0}')

    registry = ToolRegistry()
    loader = MCPLoader(mcp_json_path=mcp_json, registry=registry)

    with patch("yigthinker.mcp.loader.MCPClient", return_value=mock_client):
        await loader.load()

    assert "get_stock_price" in registry.names()

    tool = registry.get("get_stock_price")
    ctx = SessionContext()
    input_obj = tool.input_schema(ticker="AAPL")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert "100.0" in str(result.content)


async def test_loader_creates_sse_client_from_transport_field(tmp_path):
    mcp_config = {
        "mcpServers": {
            "my-sse": {
                "transport": "sse",
                "url": "http://localhost:8080/sse",
                "headers": {"Authorization": "Bearer tok"},
            }
        }
    }
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps(mcp_config))

    registry = ToolRegistry()
    loader = MCPLoader(mcp_json_path=mcp_json, registry=registry)

    with patch("yigthinker.mcp.loader.MCPClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.list_tools = AsyncMock(return_value=[])
        MockClient.return_value = mock_instance

        await loader.load()

    MockClient.assert_called_once_with(
        name="my-sse",
        transport="sse",
        url="http://localhost:8080/sse",
        headers={"Authorization": "Bearer tok"},
    )


async def test_loader_creates_http_client_from_transport_field(tmp_path):
    mcp_config = {
        "mcpServers": {
            "my-http": {
                "transport": "http",
                "url": "http://localhost:9090/mcp",
            }
        }
    }
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps(mcp_config))

    registry = ToolRegistry()
    loader = MCPLoader(mcp_json_path=mcp_json, registry=registry)

    with patch("yigthinker.mcp.loader.MCPClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.list_tools = AsyncMock(return_value=[])
        MockClient.return_value = mock_instance

        await loader.load()

    MockClient.assert_called_once_with(
        name="my-http",
        transport="http",
        url="http://localhost:9090/mcp",
        headers={},
    )


async def test_loader_defaults_to_stdio_when_no_transport(tmp_path):
    mcp_config = {
        "mcpServers": {
            "my-stdio": {
                "command": "python",
                "args": ["-m", "server"],
            }
        }
    }
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps(mcp_config))

    registry = ToolRegistry()
    loader = MCPLoader(mcp_json_path=mcp_json, registry=registry)

    with patch("yigthinker.mcp.loader.MCPClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.list_tools = AsyncMock(return_value=[])
        MockClient.return_value = mock_instance

        await loader.load()

    MockClient.assert_called_once_with(
        name="my-stdio",
        transport="stdio",
        command="python",
        args=["-m", "server"],
        env={},
    )
