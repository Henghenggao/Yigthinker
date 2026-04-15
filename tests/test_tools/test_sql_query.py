import pytest
from sqlalchemy.ext.asyncio import create_async_engine
import sqlalchemy as sa
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.tools.sql.sql_query import SqlQueryTool
from yigthinker.session import SessionContext


@pytest.fixture
async def pool_with_orders():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sa.text(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, amount REAL, region TEXT)"
        ))
        await conn.execute(sa.text(
            "INSERT INTO orders VALUES (1,100.0,'North'),(2,200.0,'South'),(3,150.0,'North')"
        ))
    pool = ConnectionPool()
    pool._engines["orders_db"] = engine
    yield pool
    await engine.dispose()


async def test_select_returns_dataframe(pool_with_orders):
    tool = SqlQueryTool(pool=pool_with_orders)
    ctx = SessionContext(settings={"connections": {"default": {"name": "orders_db"}}})
    ctx._active_connection = "orders_db"

    input_obj = tool.input_schema(query="SELECT * FROM orders", connection="orders_db")
    result = await tool.execute(input_obj, ctx)

    assert not result.is_error
    assert "orders_db" in result.content or "amount" in str(result.content)


async def test_select_registers_dataframe_in_vars(pool_with_orders):
    tool = SqlQueryTool(pool=pool_with_orders)
    ctx = SessionContext()

    input_obj = tool.input_schema(query="SELECT * FROM orders", connection="orders_db")
    result = await tool.execute(input_obj, ctx)

    assert not result.is_error
    assert "last_query" in ctx.vars
    df = ctx.vars.get("last_query")
    assert len(df) == 3
    assert list(df.columns) == ["id", "amount", "region"]


async def test_dml_requires_explicit_allow(pool_with_orders):
    tool = SqlQueryTool(pool=pool_with_orders)
    ctx = SessionContext(settings={"sandbox": {"sql_query": {"allow_dml": False}}})

    input_obj = tool.input_schema(
        query="DELETE FROM orders WHERE id=1", connection="orders_db"
    )
    result = await tool.execute(input_obj, ctx)
    assert result.is_error
    assert "DML" in result.content or "denied" in result.content.lower()
