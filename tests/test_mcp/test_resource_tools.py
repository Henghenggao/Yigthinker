from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from yigthinker.session import SessionContext


async def test_mcp_client_list_resources():
    from yigthinker.mcp.client import MCPClient

    client = MCPClient(name="test", transport="stdio", command="echo")
    # Mock the session
    mock_session = MagicMock()
    mock_resource = MagicMock()
    mock_resource.uri = "file:///data/schema.sql"
    mock_resource.name = "Schema"
    mock_resource.description = "DB schema"
    mock_session.list_resources = AsyncMock(return_value=MagicMock(resources=[mock_resource]))
    client._session = mock_session

    resources = await client.list_resources()
    assert len(resources) == 1
    assert resources[0]["uri"] == "file:///data/schema.sql"
    assert resources[0]["name"] == "Schema"


async def test_mcp_client_read_resource():
    from yigthinker.mcp.client import MCPClient

    client = MCPClient(name="test", transport="stdio", command="echo")
    mock_session = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "CREATE TABLE users (id INT);"
    mock_session.read_resource = AsyncMock(return_value=MagicMock(contents=[mock_content]))
    client._session = mock_session

    content = await client.read_resource("file:///data/schema.sql")
    assert "CREATE TABLE" in content

async def test_list_resources_tool():
    from yigthinker.mcp.resource_tools import MCPListResourcesTool, MCPListResourcesInput
    from yigthinker.mcp.client import MCPClient

    mock_client = MagicMock(spec=MCPClient)
    mock_client.name = "test-server"
    mock_client.list_resources = AsyncMock(return_value=[
        {"uri": "file:///a.sql", "name": "Schema A", "description": ""},
    ])

    tool = MCPListResourcesTool({"test-server": mock_client})
    ctx = SessionContext()
    result = await tool.execute(MCPListResourcesInput(), ctx)

    assert not result.is_error
    assert "file:///a.sql" in str(result.content)


async def test_read_resource_tool():
    from yigthinker.mcp.resource_tools import MCPReadResourceTool, MCPReadResourceInput
    from yigthinker.mcp.client import MCPClient

    mock_client = MagicMock(spec=MCPClient)
    mock_client.name = "test-server"
    mock_client.list_resources = AsyncMock(return_value=[
        {"uri": "file:///a.sql", "name": "Schema A", "description": ""},
    ])
    mock_client.read_resource = AsyncMock(return_value="CREATE TABLE users;")

    tool = MCPReadResourceTool({"test-server": mock_client})
    # Prime the URI cache
    tool._uri_to_server["file:///a.sql"] = "test-server"
    ctx = SessionContext()
    result = await tool.execute(MCPReadResourceInput(uri="file:///a.sql"), ctx)

    assert not result.is_error
    assert "CREATE TABLE" in str(result.content)


async def test_read_resource_unknown_uri():
    from yigthinker.mcp.resource_tools import MCPReadResourceTool, MCPReadResourceInput
    from yigthinker.mcp.client import MCPClient

    mock_client = MagicMock(spec=MCPClient)
    mock_client.name = "test-server"
    mock_client.list_resources = AsyncMock(return_value=[])

    tool = MCPReadResourceTool({"test-server": mock_client})
    ctx = SessionContext()
    result = await tool.execute(MCPReadResourceInput(uri="file:///unknown.sql"), ctx)

    assert result.is_error
