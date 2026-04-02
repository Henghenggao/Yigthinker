from __future__ import annotations
from typing import Any
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine


_DIALECT_MAP = {
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "sqlite": "sqlite+aiosqlite",
    "snowflake": "snowflake+snowflake-sqlalchemy",
}


class ConnectionPool:
    """Manages one AsyncEngine per named connection."""

    def __init__(self) -> None:
        self._engines: dict[str, AsyncEngine] = {}

    def add_from_config(self, name: str, config: dict[str, Any]) -> None:
        conn_type = config.get("type", "sqlite")
        dialect = _DIALECT_MAP.get(conn_type, conn_type)

        if conn_type == "sqlite":
            path = config.get("path", ":memory:")
            # Use URL.create so SQLAlchemy redacts credentials in repr/str.
            url = URL.create(drivername=dialect, database=path)
        else:
            # URL.create stores the password as a separate field and redacts it
            # from __repr__/__str__, preventing leakage through exception messages,
            # log output, LLM tool_result feedback, and session transcripts.
            url = URL.create(
                drivername=dialect,
                username=config.get("user", ""),
                password=config.get("password", "") or None,
                host=config.get("host", "localhost"),
                port=int(config["port"]) if config.get("port") else None,
                database=config.get("database", ""),
            )

        self._engines[name] = create_async_engine(url, echo=False)

    def get(self, name: str) -> AsyncEngine:
        if name not in self._engines:
            raise KeyError(f"Connection '{name}' not configured. Available: {list(self._engines)}")
        return self._engines[name]

    async def dispose_all(self) -> None:
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
