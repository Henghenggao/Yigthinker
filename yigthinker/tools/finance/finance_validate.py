from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


class ValidationRule(BaseModel):
    field: str
    required: bool = False
    min: float | None = None
    max: float | None = None
    type: Literal["number", "positive", "percentage"] | None = None


class FinanceValidateInput(BaseModel):
    action: Literal["validate", "detect_anomalies"] = "validate"

    # --- validate ---
    data: dict[str, float | None] | None = None
    rules: list[ValidationRule] | None = None

    # --- detect_anomalies ---
    values: list[float] | None = None
    labels: list[str] | None = None
    method: Literal["zscore", "iqr", "both"] = "both"
    zscore_threshold: float = 2.0
    iqr_multiplier: float = 1.5


class FinanceValidateTool:
    name = "finance_validate"
    description = (
        "Validate financial data quality or detect anomalies. "
        "action='validate': check data dict against rules (required, min/max, type). "
        "Returns quality score (completeness, consistency, accuracy). "
        "action='detect_anomalies': detect outliers in values[] using zscore, iqr, or both. "
        "Returns anomalies with severity and statistics."
    )
    input_schema = FinanceValidateInput
    is_concurrency_safe = True

    async def execute(self, input: FinanceValidateInput, ctx: SessionContext) -> ToolResult:
        try:
            if input.action == "validate":
                result = _validate(input)
            else:
                result = _detect_anomalies(input)
            return ToolResult(tool_use_id="", content=json.dumps(result))
        except ValueError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)


def _r2(val: float) -> float:
    return round(val, 2)


# ── Validation ───────────────────────────────────────────────────────────

def _validate(inp: FinanceValidateInput) -> dict:
    data = inp.data or {}
    rules = inp.rules or []
    errors: list[dict] = []
    warnings: list[dict] = []
    required_count = 0
    required_present = 0

    for rule in rules:
        val = data.get(rule.field)

        if rule.required:
            required_count += 1
            if val is None:
                errors.append({"field": rule.field, "message": f"Required field '{rule.field}' is missing"})
                continue
            required_present += 1

        if val is None:
            continue

        if rule.type == "number" and not isinstance(val, (int, float)):
            errors.append({"field": rule.field, "message": f"'{rule.field}' must be numeric"})
        if rule.type == "positive":
            if not isinstance(val, (int, float)):
                errors.append({"field": rule.field, "message": f"'{rule.field}' must be numeric"})
            elif val < 0:
                errors.append({"field": rule.field, "message": f"'{rule.field}' must be non-negative"})
            elif val == 0:
                warnings.append({"field": rule.field, "message": f"'{rule.field}' is zero"})
        if rule.type == "percentage":
            if isinstance(val, (int, float)) and (val < 0 or val > 100):
                warnings.append({"field": rule.field, "message": f"'{rule.field}' ({val}) outside 0-100% range"})

        if rule.min is not None and isinstance(val, (int, float)) and val < rule.min:
            errors.append({"field": rule.field, "message": f"'{rule.field}' ({val}) below minimum {rule.min}"})
        if rule.max is not None and isinstance(val, (int, float)) and val > rule.max:
            errors.append({"field": rule.field, "message": f"'{rule.field}' ({val}) above maximum {rule.max}"})

    # Consistency checks
    inconsistencies = 0
    rev = data.get("revenue")
    costs = data.get("costs")
    if rev and costs and isinstance(rev, (int, float)) and isinstance(costs, (int, float)):
        if rev > 0 and costs / rev > 0.9:
            warnings.append({"field": "costs", "message": "Cost ratio exceeds 90% of revenue",
                             "suggestion": "Verify cost figures"})
            inconsistencies += 1
        ni = data.get("net_income")
        if ni is not None and isinstance(ni, (int, float)) and rev > 0:
            margin = ni / rev * 100
            if margin < 5:
                warnings.append({"field": "net_income", "message": f"Profit margin is only {_r2(margin)}%"})

    assets = data.get("assets")
    liabilities = data.get("liabilities")
    equity = data.get("equity")
    if all(isinstance(v, (int, float)) for v in [assets, liabilities, equity] if v is not None):
        if assets is not None and liabilities is not None and equity is not None:
            diff = abs(assets - liabilities - equity)
            if diff > 0.01 * max(abs(assets), 1):
                errors.append({"field": "accounting_equation",
                               "message": f"Assets - Liabilities ≠ Equity (diff: {_r2(diff)})"})
                inconsistencies += 1

    # Quality scores
    completeness = required_present / required_count if required_count > 0 else 1.0
    consistency = max(0.0, 1.0 - len(errors) * 0.1 - inconsistencies * 0.1)
    accuracy = max(0.0, 1.0 - len(warnings) * 0.05)
    overall = _r2(completeness * 0.4 + consistency * 0.3 + accuracy * 0.3)

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "quality": {
            "completeness": _r2(completeness),
            "consistency": _r2(consistency),
            "accuracy": _r2(accuracy),
            "overall": overall,
        },
    }


# ── Anomaly Detection ────────────────────────────────────────────────────

def _detect_anomalies(inp: FinanceValidateInput) -> dict:
    vals = inp.values
    if not vals or len(vals) < 3:
        raise ValueError("values must contain at least 3 data points")

    n = len(vals)
    mean = sum(vals) / n
    variance = sum((v - mean) ** 2 for v in vals) / n
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    sorted_vals = sorted(vals)
    if n % 2 == 0:
        median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    else:
        median = sorted_vals[n // 2]

    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1
    lower = q1 - inp.iqr_multiplier * iqr
    upper = q3 + inp.iqr_multiplier * iqr

    anomalies: list[dict] = []
    seen_indices: set[int] = set()

    for i, v in enumerate(vals):
        label = inp.labels[i] if inp.labels and i < len(inp.labels) else None

        # Z-score method
        if inp.method in ("zscore", "both") and std_dev > 0:
            z = (v - mean) / std_dev
            if abs(z) > inp.zscore_threshold:
                severity = "critical" if abs(z) > inp.zscore_threshold * 1.5 else "warning"
                if i not in seen_indices:
                    entry: dict = {"index": i, "value": v, "zscore": _r2(z),
                                   "method": "zscore", "severity": severity}
                    if label:
                        entry["label"] = label
                    anomalies.append(entry)
                    seen_indices.add(i)

        # IQR method
        if inp.method in ("iqr", "both"):
            if v < lower or v > upper:
                severity = "critical" if (v < q1 - 3 * iqr or v > q3 + 3 * iqr) else "warning"
                if i not in seen_indices:
                    entry = {"index": i, "value": v, "method": "iqr", "severity": severity}
                    if label:
                        entry["label"] = label
                    anomalies.append(entry)
                    seen_indices.add(i)

    summary = f"Found {len(anomalies)} anomalies in {n} values"
    if anomalies:
        critical = sum(1 for a in anomalies if a["severity"] == "critical")
        summary += f" ({critical} critical, {len(anomalies) - critical} warning)"

    return {
        "anomalies": anomalies,
        "statistics": {
            "mean": _r2(mean),
            "median": _r2(median),
            "std_dev": _r2(std_dev),
            "q1": _r2(q1),
            "q3": _r2(q3),
            "iqr": _r2(iqr),
            "lower_bound": _r2(lower),
            "upper_bound": _r2(upper),
        },
        "summary": summary,
    }
