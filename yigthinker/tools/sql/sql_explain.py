from __future__ import annotations
import re
import sqlalchemy as sa
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool

_DML_KEYWORDS = re.compile(
    r"\b(DELETE|INSERT|UPDATE|DROP|TRUNCATE|ALTER|CREATE|COPY|MERGE|CALL|GRANT|REVOKE|EXEC)\b",
    re.IGNORECASE,
)


class SqlExplainInput(BaseModel):
    query: str
    connection: str = "default"


class SqlExplainTool:
    name = "sql_explain"
    description = (
        "Show the execution plan for a SQL query without running it. "
        "Only SELECT queries are allowed — DML statements are rejected."
    )
    input_schema = SqlExplainInput

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    async def execute(self, input: SqlExplainInput, ctx: SessionContext) -> ToolResult:
        if _DML_KEYWORDS.search(input.query):
            return ToolResult(
                tool_use_id="",
                content="DML statements are not allowed in sql_explain. Only SELECT queries can be explained.",
                is_error=True,
            )

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
