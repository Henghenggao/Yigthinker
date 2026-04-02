from __future__ import annotations
from typing import Any
import pandas as pd

_SAMPLE_ROWS = 10  # rows to include in summarized result


class ContextManager:
    """Token budget tracking and large result summarization.

    Token budget fractions (from spec):
        system prompt   20%
        data context    30%  (schemas + samples injected by tools)
        session history 40%
        reserve buffer  10%
    """

    SYSTEM_FRACTION = 0.20
    DATA_CONTEXT_FRACTION = 0.30
    HISTORY_FRACTION = 0.40
    RESERVE_FRACTION = 0.10

    def __init__(self, max_tokens: int = 200_000) -> None:
        self._max_tokens = max_tokens

    @property
    def history_budget(self) -> int:
        return int(self._max_tokens * self.HISTORY_FRACTION)

    def summarize_dataframe_result(self, df: pd.DataFrame) -> dict[str, Any]:
        """Return full records for small DataFrames; summary for large ones.

        Threshold: > 10 rows triggers summarization. Full data stays in the
        VarRegistry, not in the message history.
        """
        if len(df) <= _SAMPLE_ROWS:
            return {"type": "dataframe", "data": df.to_dict(orient="records")}

        return {
            "type": "dataframe_summary",
            "total_rows": len(df),
            "columns": list(df.columns),
            "sample": df.head(_SAMPLE_ROWS).to_dict(orient="records"),
            "stats": df.describe(include="all").to_dict(),
            "note": (
                f"Full dataset ({len(df):,} rows) stored in variable registry. "
                f"Showing first {_SAMPLE_ROWS} rows + statistical summary."
            ),
        }
