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


async def test_sse_client_start_calls_sse_transport():
    client = MCPClient(name="test-sse", transport="sse", url="http://localhost:8080/sse")

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))

    with patch("yigthinker.mcp.client.sse_client", return_value=mock_cm) as mock_sse, \
         patch("yigthinker.mcp.client.ClientSession", return_value=mock_session):
        await client.start()

    mock_sse.assert_called_once_with("http://localhost:8080/sse", headers={})


async def test_http_client_start_calls_streamablehttp_transport():
    client = MCPClient(name="test-http", transport="http", url="http://localhost:9090/mcp")

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock(), MagicMock()))

    with patch("yigthinker.mcp.client.streamablehttp_client", return_value=mock_cm) as mock_http, \
         patch("yigthinker.mcp.client.ClientSession", return_value=mock_session):
        await client.start()

    mock_http.assert_called_once_with("http://localhost:9090/mcp", headers={})


async def test_stdio_client_transport_backward_compatible():
    client = MCPClient(name="test-stdio", transport="stdio", command="python", args=["-m", "server"])

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))

    with patch("yigthinker.mcp.client.stdio_client", return_value=mock_cm), \
         patch("yigthinker.mcp.client.ClientSession", return_value=mock_session):
        await client.start()
