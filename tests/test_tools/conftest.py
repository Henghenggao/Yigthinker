# tests/test_tools/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
import sqlalchemy as sa

@pytest.fixture
async def sqlite_engine():
    """In-memory SQLite engine with a sample orders table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount REAL, region TEXT)")
        )
        await conn.execute(
            sa.text("INSERT INTO orders VALUES (1, 100.0, 'North'), (2, 200.0, 'South'), (3, 150.0, 'North')")
        )
    yield engine
    await engine.dispose()
