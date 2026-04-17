from __future__ import annotations
import re
import pandas as pd
import sqlalchemy as sa
from pydantic import BaseModel
from yigthinker.types import DryRunReceipt, ToolResult
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool

_DML_KEYWORDS = re.compile(
    r"\b(DELETE|INSERT|UPDATE|DROP|TRUNCATE|ALTER|CREATE|COPY|MERGE|CALL|GRANT|REVOKE|EXEC)\b",
    re.IGNORECASE,
)


class SqlQueryInput(BaseModel):
    query: str
    connection: str = "default"


class SqlQueryTool:
    name = "sql_query"
    description = (
        "Execute a SQL SELECT query against a configured database connection. "
        "Stores the result as 'last_query' in the DataFrame variable registry. "
        "DML statements (DELETE, INSERT, UPDATE, DROP) are blocked by default."
    )
    input_schema = SqlQueryInput

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    async def execute(self, input: SqlQueryInput, ctx: SessionContext) -> ToolResult:
        if ctx.dry_run and _DML_KEYWORDS.search(input.query):
            return ToolResult(
                tool_use_id="",
                content=DryRunReceipt(
                    tool_name=self.name,
                    summary=f"Would execute DML ({len(input.query)} chars)",
                    details={
                        "input": input.model_dump(),
                        "sql_head": input.query[:200],
                    },
                ),
            )
        # SELECT queries continue to execute in dry_run — they are read-only.

        if _DML_KEYWORDS.search(input.query):
            allow_dml = (
                ctx.settings
                .get("sandbox", {})
                .get("sql_query", {})
                .get("allow_dml", False)
            )
            if not allow_dml:
                return ToolResult(
                    tool_use_id="",
                    content="DML statements (DELETE/INSERT/UPDATE/DROP) are not allowed in read-only mode. Set sandbox.sql_query.allow_dml=true to enable.",
                    is_error=True,
                )

        try:
            engine = self._pool.get(input.connection)
            async with engine.connect() as conn:
                result = await conn.execute(sa.text(input.query))
                rows = result.fetchall()
                columns = list(result.keys())

            df = pd.DataFrame(rows, columns=columns)
            ctx.vars.set("last_query", df)

            cm = ctx.context_manager
            return ToolResult(
                tool_use_id="",
                content=cm.summarize_dataframe_result(df),
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
