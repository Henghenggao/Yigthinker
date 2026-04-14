from __future__ import annotations
from typing import Any
import sqlalchemy as sa
from pydantic import BaseModel, Field
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool


class SchemaInspectInput(BaseModel):
    connection: str = "default"
    table: str | None = None
    sample_rows: int = Field(default=3, ge=0, le=100)


class SchemaInspectTool:
    name = "schema_inspect"
    description = (
        "View database schema: list tables, columns, types, and sample rows. "
        "Always read-only. Output is injected into the Context Manager as data context."
    )
    input_schema = SchemaInspectInput
    is_concurrency_safe = True

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    async def execute(self, input: SchemaInspectInput, ctx: SessionContext) -> ToolResult:
        try:
            engine = self._pool.get(input.connection)
            schema: dict[str, Any] = {}

            async with engine.connect() as conn:
                table_names = await conn.run_sync(
                    lambda sync_conn: sa.inspect(sync_conn).get_table_names()
                )

                if input.table:
                    # Validate against the real table list — prevents SQL injection
                    # via subquery or multi-statement injection through input.table.
                    if input.table not in table_names:
                        return ToolResult(
                            tool_use_id="",
                            content=f"Table '{input.table}' not found. Available: {table_names}",
                            is_error=True,
                        )
                    table_names = [input.table]

                for tbl in table_names:
                    columns = await conn.run_sync(
                        lambda sync_conn, t=tbl: [
                            {"name": c["name"], "type": str(c["type"])}
                            for c in sa.inspect(sync_conn).get_columns(t)
                        ]
                    )
                    sample: list[dict] = []
                    if input.sample_rows > 0:
                        sample = await conn.run_sync(
                            lambda sync_conn, t=tbl, limit=input.sample_rows: _fetch_sample_rows(
                                sync_conn,
                                t,
                                limit,
                            )
                        )

                    schema[tbl] = {"columns": columns, "sample": sample}

            return ToolResult(tool_use_id="", content=schema)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)


def _fetch_sample_rows(
    sync_conn: sa.Connection,
    table_name: str,
    sample_rows: int,
) -> list[dict[str, Any]]:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=sync_conn)
    result = sync_conn.execute(sa.select(table).limit(sample_rows))
    return [dict(row) for row in result.mappings().all()]
