# tests/test_tools/test_sql_connection.py
import pytest
from yigthinker.tools.sql.connection import ConnectionPool

async def test_get_engine_returns_engine(sqlite_engine):
    pool = ConnectionPool()
    pool._engines["test"] = sqlite_engine
    engine = pool.get("test")
    assert engine is sqlite_engine

def test_get_missing_raises():
    pool = ConnectionPool()
    with pytest.raises(KeyError, match="no_such_conn"):
        pool.get("no_such_conn")

async def test_from_config_sqlite(tmp_path):
    config = {
        "type": "sqlite",
        "path": str(tmp_path / "test.db"),
    }
    pool = ConnectionPool()
    pool.add_from_config("mydb", config)
    engine = pool.get("mydb")
    assert engine is not None
    await engine.dispose()
