from __future__ import annotations
import sqlalchemy as sa
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool


class SqlExplainInput(BaseModel):
    query: str
    connection: str = "default"


class SqlExplainTool:
    name = "sql_explain"
    description = (
        "Show the execution plan for a SQL query without running it. "
        "Always read-only and safe to call."
    )
    input_schema = SqlExplainInput

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    async def execute(self, input: SqlExplainInput, ctx: SessionContext) -> ToolResult:
        try:
            engine = self._pool.get(input.connection)
            dialect = engine.dialect.name
            prefix = "EXPLAIN QUERY PLAN" if dialect == "sqlite" else "EXPLAIN"

            async with engine.connect() as conn:
                result = await conn.execute(sa.text(f"{prefix} {input.query}"))
                rows = result.fetchall()

            plan = "\n".join(str(row) for row in rows)
            return ToolResult(tool_use_id="", content=plan)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
