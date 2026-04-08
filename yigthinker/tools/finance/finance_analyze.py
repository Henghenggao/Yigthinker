from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult

AnalysisType = Literal["ratios", "trends", "variance", "scenario", "sensitivity"]


class FinanceAnalyzeInput(BaseModel):
    analysis_type: AnalysisType

    # --- ratios / sensitivity ---
    revenue: float | None = None
    costs: float | None = None
    net_income: float | None = None
    assets: float | None = None
    liabilities: float | None = None
    equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None

    # --- trends ---
    values: list[float] | None = None
    labels: list[str] | None = None

    # --- variance ---
    actual: list[float] | None = None
    budget: list[float] | None = None
    categories: list[str] | None = None

    # --- scenario ---
    base_case: dict[str, float] | None = None
    scenarios: list[dict] | None = None
    output_metrics: list[str] | None = None


class FinanceAnalyzeTool:
    name = "finance_analyze"
    description = (
        "Perform financial analysis. Types: "
        "ratios (profitability/liquidity/leverage from revenue, costs, assets, liabilities, equity, etc.), "
        "trends (average period-over-period change from values[]), "
        "variance (actual[] vs budget[] comparison), "
        "scenario (multi-scenario modeling with base_case, scenarios[], output_metrics[]), "
        "sensitivity (revenue/cost impact analysis)."
    )
    input_schema = FinanceAnalyzeInput

    async def execute(self, input: FinanceAnalyzeInput, ctx: SessionContext) -> ToolResult:
        try:
            handler = _ANALYSIS_HANDLERS.get(input.analysis_type)
            if handler is None:
                return ToolResult(
                    tool_use_id="",
                    content=f"Unknown analysis_type '{input.analysis_type}'.",
                    is_error=True,
                )
            result = handler(input)
            return ToolResult(tool_use_id="", content=json.dumps(result))
        except (ValueError, ZeroDivisionError) as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)


def _r2(val: float) -> float:
    return round(val, 2)


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ── Ratios ───────────────────────────────────────────────────────────────

def _ratios(inp: FinanceAnalyzeInput) -> dict:
    results: dict = {}
    insights: list[str] = []

    # Profitability
    prof: dict = {}
    if inp.revenue and inp.costs:
        gm = _r2((inp.revenue - inp.costs) / inp.revenue * 100)
        prof["gross_margin"] = gm
        insights.append(f"Gross margin: {gm}%")
    if inp.net_income is not None and inp.revenue:
        nm = _r2(inp.net_income / inp.revenue * 100)
        prof["net_margin"] = nm
        insights.append(f"Net margin: {nm}%")
    if inp.net_income is not None and inp.assets:
        roa = _r2(inp.net_income / inp.assets * 100)
        prof["return_on_assets"] = roa
        insights.append(f"Return on assets: {roa}%")
    if inp.net_income is not None and inp.equity:
        roe = _r2(inp.net_income / inp.equity * 100)
        prof["return_on_equity"] = roe
        insights.append(f"Return on equity: {roe}%")
    if prof:
        results["profitability"] = prof

    # Liquidity
    liq: dict = {}
    if inp.current_assets is not None and inp.current_liabilities:
        cr = _r2(inp.current_assets / inp.current_liabilities)
        liq["current_ratio"] = cr
        health = "healthy" if cr >= 1.5 else ("adequate" if cr >= 1.0 else "concerning")
        insights.append(f"Current ratio: {cr} ({health})")
    if inp.current_assets is not None and inp.current_liabilities and inp.inventory is not None:
        qr = _r2((inp.current_assets - inp.inventory) / inp.current_liabilities)
        liq["quick_ratio"] = qr
        insights.append(f"Quick ratio: {qr}")
    if liq:
        results["liquidity"] = liq

    # Leverage
    lev: dict = {}
    if inp.liabilities is not None and inp.equity:
        de = _r2(inp.liabilities / inp.equity)
        lev["debt_to_equity"] = de
        insights.append(f"Debt-to-equity: {de}")
    if inp.liabilities is not None and inp.assets:
        da = _r2(inp.liabilities / inp.assets * 100)
        lev["debt_to_assets"] = da
        insights.append(f"Debt-to-assets: {da}%")
    if lev:
        results["leverage"] = lev

    if not results:
        raise ValueError("Insufficient data for ratio analysis. Provide revenue, costs, assets, liabilities, or equity.")

    return {"analysis_type": "ratios", "results": results, "insights": insights}


# ── Trends ───────────────────────────────────────────────────────────────

def _trends(inp: FinanceAnalyzeInput) -> dict:
    vals = inp.values
    if not vals or len(vals) < 2:
        raise ValueError("values must contain at least 2 data points")

    changes: list[float] = []
    for i in range(1, len(vals)):
        if vals[i - 1] != 0:
            changes.append((vals[i] - vals[i - 1]) / vals[i - 1] * 100)

    avg_change = _r2(sum(changes) / len(changes)) if changes else 0.0
    direction = "upward" if avg_change > 1 else ("downward" if avg_change < -1 else "stable")

    period_details: list[dict] = []
    for i, ch in enumerate(changes):
        detail: dict = {"period": i + 1, "change_pct": _r2(ch)}
        if inp.labels and i + 1 < len(inp.labels):
            detail["label"] = inp.labels[i + 1]
        period_details.append(detail)

    return {
        "analysis_type": "trends",
        "average_change_pct": avg_change,
        "direction": direction,
        "periods": period_details,
        "insights": [f"Average period-over-period change: {avg_change}% ({direction} trend)"],
    }


# ── Variance ─────────────────────────────────────────────────────────────

def _variance(inp: FinanceAnalyzeInput) -> dict:
    actual = inp.actual
    budget = inp.budget
    if not actual or not budget:
        raise ValueError("Both actual and budget arrays are required")
    if len(actual) != len(budget):
        raise ValueError("actual and budget arrays must have the same length")

    cats = inp.categories or [f"Item {i+1}" for i in range(len(actual))]
    variances: list[dict] = []
    total_actual = 0.0
    total_budget = 0.0

    for i in range(len(actual)):
        a, b = actual[i], budget[i]
        total_actual += a
        total_budget += b
        var = _r2(a - b)
        var_pct = _r2(var / b * 100) if b != 0 else 0.0
        if abs(var_pct) < 5:
            status = "neutral"
        elif var >= 0:
            status = "favorable"
        else:
            status = "unfavorable"
        variances.append({
            "category": cats[i] if i < len(cats) else f"Item {i+1}",
            "actual": a,
            "budget": b,
            "variance": var,
            "variance_pct": var_pct,
            "status": status,
        })

    total_var = _r2(total_actual - total_budget)
    total_var_pct = _r2(total_var / total_budget * 100) if total_budget != 0 else 0.0
    fav = sum(1 for v in variances if v["status"] == "favorable")
    unfav = sum(1 for v in variances if v["status"] == "unfavorable")

    return {
        "analysis_type": "variance",
        "variances": variances,
        "total_variance": total_var,
        "total_variance_pct": total_var_pct,
        "insights": [
            f"Total variance: {total_var} ({total_var_pct}%)",
            f"{fav} favorable, {unfav} unfavorable line items",
        ],
    }


# ── Scenario ─────────────────────────────────────────────────────────────

def _scenario_outputs(inputs: dict[str, float]) -> dict[str, float]:
    revenue = inputs.get("revenue", inputs.get("sales", 0))
    if "price" in inputs and "quantity" in inputs:
        revenue = revenue or inputs["price"] * inputs["quantity"]
    costs = inputs.get("costs", inputs.get("expenses", 0))
    if "unit_cost" in inputs and "quantity" in inputs:
        costs = costs or inputs["unit_cost"] * inputs["quantity"]
    tax = inputs.get("tax_rate", 0)
    gross = revenue - costs
    net = gross * (1 - tax) if tax else gross
    margin = _r2(net / revenue * 100) if revenue else 0
    return {"revenue": _r2(revenue), "costs": _r2(costs),
            "gross_profit": _r2(gross), "net_income": _r2(net), "margin": margin}


def _scenario(inp: FinanceAnalyzeInput) -> dict:
    base = inp.base_case
    scenarios = inp.scenarios
    if not base or not scenarios:
        raise ValueError("base_case and scenarios are required")

    base_out = _scenario_outputs(base)
    results: list[dict] = []
    primary = "net_income"

    for sc in scenarios:
        name = sc.get("name", "Unnamed")
        assumptions = sc.get("assumptions", {})
        merged = {**base, **assumptions}
        outputs = _scenario_outputs(merged)

        # Sensitivity: % change of each variable vs base
        sensitivity: dict[str, float] = {}
        for key, val in assumptions.items():
            bv = base.get(key, 0)
            if bv != 0:
                sensitivity[key] = _r2((val - bv) / abs(bv) * 100)
            else:
                sensitivity[key] = 100.0 if val != 0 else 0.0

        results.append({
            "name": name,
            "inputs": merged,
            "outputs": outputs,
            "sensitivity": sensitivity,
        })

    sorted_by = sorted(results, key=lambda r: r["outputs"].get(primary, 0), reverse=True)
    best = sorted_by[0]["name"] if sorted_by else "N/A"
    worst = sorted_by[-1]["name"] if sorted_by else "N/A"

    comparison: dict = {"best_case": best, "worst_case": worst}
    # Probability-weighted value if probabilities provided
    probs = [sc.get("probability", 0) for sc in scenarios]
    if all(p > 0 for p in probs) and abs(sum(probs) - 1.0) < 0.05:
        pw = sum(
            r["outputs"].get(primary, 0) * sc.get("probability", 0)
            for r, sc in zip(results, scenarios)
        )
        comparison["probability_weighted"] = _r2(pw)

    return {
        "analysis_type": "scenario",
        "base_case": {"inputs": base, "outputs": base_out},
        "scenarios": results,
        "comparison": comparison,
        "insights": [f"Best case: {best}, Worst case: {worst}"],
    }


# ── Sensitivity ──────────────────────────────────────────────────────────

def _sensitivity(inp: FinanceAnalyzeInput) -> dict:
    if not inp.revenue or not inp.costs:
        raise ValueError("revenue and costs are required for sensitivity analysis")

    margin = inp.revenue - inp.costs
    rev_sens = _r2(margin / inp.revenue * 100)
    cost_sens = _r2(margin / inp.costs * 100)

    rev_impact = _r2(rev_sens * 0.1)
    cost_impact = _r2(cost_sens * 0.1)

    return {
        "analysis_type": "sensitivity",
        "margin": _r2(margin),
        "revenue_sensitivity_pct": rev_sens,
        "cost_sensitivity_pct": cost_sens,
        "insights": [
            f"10% change in revenue impacts profit by ~{rev_impact}%",
            f"10% change in costs impacts profit by ~{cost_impact}%",
            f"{'Revenue' if abs(rev_impact) > abs(cost_impact) else 'Costs'} is the more sensitive variable.",
        ],
    }


_ANALYSIS_HANDLERS: dict[str, callable] = {
    "ratios": _ratios,
    "trends": _trends,
    "variance": _variance,
    "scenario": _scenario,
    "sensitivity": _sensitivity,
}
