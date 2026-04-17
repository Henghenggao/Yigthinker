from unittest.mock import AsyncMock, MagicMock, patch
from yigthinker.presence.cli.repl import Repl
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool


async def test_repl_handles_slash_command():
    ctx = SessionContext()
    pool = ConnectionPool()
    mock_loop = AsyncMock()

    repl = Repl(agent_loop=mock_loop, ctx=ctx, pool=pool)
    with patch.object(repl._commands, "handle", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = MagicMock(handled=True, output="vars output")
        output = await repl.process_input("/vars")

    mock_loop.run.assert_not_called()
    assert output == "vars output"


async def test_repl_routes_query_to_agent():
    ctx = SessionContext()
    pool = ConnectionPool()
    mock_loop = AsyncMock()
    mock_loop.run = AsyncMock(return_value="Agent response")

    repl = Repl(agent_loop=mock_loop, ctx=ctx, pool=pool)
    output = await repl.process_input("show me revenue by region")

    mock_loop.run.assert_called_once_with("show me revenue by region", ctx)
    assert output == "Agent response"
