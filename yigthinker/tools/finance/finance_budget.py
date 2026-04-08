from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult

_INCOME_KEYWORDS = {"revenue", "income", "sales", "earnings", "receipts"}


class FinanceBudgetInput(BaseModel):
    period: Literal["monthly", "quarterly", "annual"]
    categories: list[str]


class FinanceBudgetTool:
    name = "finance_budget"
    description = (
        "Generate a budget planning template for a specified period and categories. "
        "Each category is auto-classified as 'income' or 'expense' based on its name. "
        "Returns a structured template with planned/actual/variance fields ready to fill."
    )
    input_schema = FinanceBudgetInput

    async def execute(self, input: FinanceBudgetInput, ctx: SessionContext) -> ToolResult:
        if not input.categories:
            return ToolResult(
                tool_use_id="",
                content="At least one category is required.",
                is_error=True,
            )

        cat_entries: list[dict] = []
        for name in input.categories:
            lower = name.lower()
            cat_type = "income" if any(kw in lower for kw in _INCOME_KEYWORDS) else "expense"
            cat_entries.append({
                "name": name,
                "type": cat_type,
                "planned": 0,
                "actual": 0,
                "variance": 0,
            })

        result = {
            "period": input.period,
            "categories": cat_entries,
            "summary": {
                "total_income": 0,
                "total_expenses": 0,
                "net_cash_flow": 0,
            },
        }

        return ToolResult(tool_use_id="", content=json.dumps(result))
