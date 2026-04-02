import pytest
from sqlalchemy.ext.asyncio import create_async_engine
import sqlalchemy as sa
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.tools.sql.sql_explain import SqlExplainTool
from yigthinker.session import SessionContext


@pytest.fixture
async def pool():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE TABLE t (id INTEGER, val TEXT)"))
    pool = ConnectionPool()
    pool._engines["db"] = engine
    yield pool
    await engine.dispose()


async def test_explain_returns_plan(pool):
    tool = SqlExplainTool(pool=pool)
    ctx = SessionContext()
    input_obj = tool.input_schema(query="SELECT * FROM t WHERE id=1", connection="db")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    assert result.content is not None
