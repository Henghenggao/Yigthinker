from __future__ import annotations
from collections import defaultdict
from typing import Any


class StatsAccumulator:
    """In-memory stats accumulator. Attached to SessionContext."""

    def __init__(self) -> None:
        self._counters: dict[str, int | float] = defaultdict(int)
        self._connection_usage: dict[str, int] = defaultdict(int)
        self._top_tables: dict[str, int] = defaultdict(int)

    def increment(self, key: str, by: int = 1) -> None:
        self._counters[key] += by

    def add(self, key: str, value: int | float) -> None:
        self._counters[key] += value

    def get(self, key: str, default: int = 0) -> int | float:
        return self._counters.get(key, default)

    def add_connection_usage(self, connection: str) -> None:
        self._connection_usage[connection] += 1

    def get_connection_usage(self) -> dict[str, int]:
        return dict(self._connection_usage)

    def add_table_usage(self, tables: list[str]) -> None:
        for t in tables:
            self._top_tables[t] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._counters,
            "connection_usage": dict(self._connection_usage),
            "top_tables": dict(sorted(self._top_tables.items(), key=lambda x: -x[1])[:10]),
        }

    def format_session_report(self) -> str:
        c = self._counters
        lines = [
            "Session Stats",
            "\u2500" * 40,
            f"SQL queries:      {c.get('sql_queries_count', 0):>6}  \u2502  Rows scanned:    {c.get('sql_rows_scanned', 0):>10,}",
            f"DataFrame ops:    {c.get('df_operations_count', 0):>6}  \u2502  Rows processed:  {c.get('df_rows_processed', 0):>10,}",
            f"Charts created:   {c.get('charts_created', 0):>6}  \u2502  Reports:         {c.get('reports_generated', 0):>6}",
            f"Forecasts:        {c.get('forecasts_run', 0):>6}",
        ]
        if self._connection_usage:
            lines.append("")
            lines.append("Data Sources")
            lines.append("\u2500" * 40)
            for conn, count in self._connection_usage.items():
                lines.append(f"  {conn}: {count} queries")
        return "\n".join(lines)
