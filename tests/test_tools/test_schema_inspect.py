import pytest
from sqlalchemy.ext.asyncio import create_async_engine
import sqlalchemy as sa
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.tools.sql.schema_inspect import SchemaInspectTool
from yigthinker.session import SessionContext


@pytest.fixture
async def pool_with_tables():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sa.text(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
        ))
        await conn.execute(sa.text(
            "INSERT INTO customers VALUES (1,'Alice','a@test.com'),(2,'Bob','b@test.com')"
        ))
    pool = ConnectionPool()
    pool._engines["crm"] = engine
    yield pool
    await engine.dispose()


async def test_inspect_lists_tables(pool_with_tables):
    tool = SchemaInspectTool(pool=pool_with_tables)
    ctx = SessionContext()
    input_obj = tool.input_schema(connection="crm")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    schema = result.content
    assert "customers" in str(schema)


async def test_inspect_shows_columns(pool_with_tables):
    tool = SchemaInspectTool(pool=pool_with_tables)
    ctx = SessionContext()
    input_obj = tool.input_schema(connection="crm", table="customers")
    result = await tool.execute(input_obj, ctx)
    assert not result.is_error
    schema = result.content
    assert "name" in str(schema)
    assert "email" in str(schema)


async def test_inspect_includes_sample_rows(pool_with_tables):
    tool = SchemaInspectTool(pool=pool_with_tables)
    ctx = SessionContext()
    input_obj = tool.input_schema(connection="crm", table="customers", sample_rows=2)
    result = await tool.execute(input_obj, ctx)
    content = result.content
    assert "Alice" in str(content) or "sample" in str(content)
