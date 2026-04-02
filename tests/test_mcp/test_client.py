from unittest.mock import AsyncMock, MagicMock, patch

from yigthinker.mcp.client import MCPClient


async def test_list_tools_returns_tool_defs():
    client = MCPClient(name="test", command="echo", args=[])

    mock_session = AsyncMock()
    mock_tool = MagicMock()
    mock_tool.name = "get_price"
    mock_tool.description = "Get stock price"
    mock_tool.inputSchema = {"type": "object", "properties": {"ticker": {"type": "string"}}}
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[mock_tool]))

    with patch.object(client, "_session", mock_session):
        tools = await client.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "get_price"
    assert tools[0].description == "Get stock price"


async def test_call_tool_returns_result():
    client = MCPClient(name="test", command="echo", args=[])

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(
        return_value=MagicMock(content=[MagicMock(type="text", text='{"price": 150.0}')])
    )

    with patch.object(client, "_session", mock_session):
        result = await client.call_tool("get_price", {"ticker": "AAPL"})

    assert result == '{"price": 150.0}'
