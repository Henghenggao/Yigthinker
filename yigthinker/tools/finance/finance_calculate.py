from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult

Metric = Literal[
    "roi", "npv", "irr", "breakeven", "pmt", "fv", "pv", "wacc", "depreciation",
]


class FinanceCalculateInput(BaseModel):
    metric: Metric
    # ROI
    gain: float | None = None
    cost: float | None = None
    # NPV / IRR
    rate: float | None = None
    cash_flows: list[float] | None = None
    # Breakeven
    fixed_costs: float | None = None
    price_per_unit: float | None = None
    variable_cost_per_unit: float | None = None
    # PMT / FV / PV
    nper: int | None = None
    pmt: float | None = None
    pv: float | None = None
    fv: float | None = None
    payment_type: Literal[0, 1] = 0  # 0=end, 1=beginning
    # WACC
    equity: float | None = None
    debt: float | None = None
    cost_of_equity: float | None = None
    cost_of_debt: float | None = None
    tax_rate: float | None = None
    # Depreciation
    salvage: float | None = None
    life: int | None = None
    method: str | None = None  # "straight-line" | "declining-balance" | "sum-of-years"
    period: int | None = None


class FinanceCalculateTool:
    name = "finance_calculate"
    description = (
        "Calculate financial metrics. Supported metrics: "
        "roi (gain, cost), "
        "npv (rate, cash_flows), "
        "irr (cash_flows), "
        "breakeven (fixed_costs, price_per_unit, variable_cost_per_unit), "
        "pmt (rate, nper, pv, fv?, payment_type?), "
        "fv (rate, nper, pmt, pv?, payment_type?), "
        "pv (rate, nper, pmt, fv?, payment_type?), "
        "wacc (equity, debt, cost_of_equity, cost_of_debt, tax_rate), "
        "depreciation (cost, salvage, life, method, period?)."
    )
    input_schema = FinanceCalculateInput

    async def execute(self, input: FinanceCalculateInput, ctx: SessionContext) -> ToolResult:
        try:
            handler = _HANDLERS.get(input.metric)
            if handler is None:
                return ToolResult(
                    tool_use_id="",
                    content=f"Unknown metric '{input.metric}'.",
                    is_error=True,
                )
            result = handler(input)
            return ToolResult(tool_use_id="", content=json.dumps(result))
        except (ValueError, ZeroDivisionError) as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)


def _require(val: object, name: str) -> float:
    if val is None:
        raise ValueError(f"'{name}' is required for this metric")
    return float(val)


def _r2(val: float) -> float:
    return round(val, 2)


def _roi(inp: FinanceCalculateInput) -> dict:
    gain = _require(inp.gain, "gain")
    cost = _require(inp.cost, "cost")
    if cost == 0:
        raise ValueError("cost must not be zero")
    value = _r2((gain - cost) / cost * 100)
    if value > 0:
        interp = f"Positive ROI of {value}% indicates a profitable investment."
    elif value < 0:
        interp = f"Negative ROI of {value}% indicates a loss on investment."
    else:
        interp = "Break-even: gains exactly match costs."
    return {"metric": "roi", "value": value, "interpretation": interp,
            "formula": "ROI = (Gain - Cost) / Cost × 100%"}


def _npv(inp: FinanceCalculateInput) -> dict:
    rate = _require(inp.rate, "rate")
    cfs = inp.cash_flows
    if not cfs:
        raise ValueError("cash_flows must be a non-empty list")
    value = _r2(sum(cf / (1 + rate) ** t for t, cf in enumerate(cfs)))
    interp = ("Positive NPV suggests the investment is profitable at the given discount rate."
              if value >= 0
              else "Negative NPV suggests the investment does not meet the required rate of return.")
    return {"metric": "npv", "value": value, "interpretation": interp,
            "formula": "NPV = Σ(Cash Flow_t / (1 + r)^t)"}


def _irr(inp: FinanceCalculateInput) -> dict:
    cfs = inp.cash_flows
    if not cfs or len(cfs) < 2:
        raise ValueError("cash_flows must have at least 2 values")

    # Newton-Raphson
    irr = 0.1
    for _ in range(100):
        npv = sum(cf / (1 + irr) ** t for t, cf in enumerate(cfs))
        dnpv = sum(-t * cf / (1 + irr) ** (t + 1) for t, cf in enumerate(cfs))
        if abs(dnpv) < 1e-12:
            break
        new_irr = irr - npv / dnpv
        if abs(new_irr - irr) < 0.0001:
            irr = new_irr
            break
        irr = new_irr

    value = _r2(irr * 100)
    interp = f"IRR of {value}%. Compare against your required rate of return to evaluate the investment."
    return {"metric": "irr", "value": value, "interpretation": interp,
            "formula": "IRR is the rate where NPV = 0"}


def _breakeven(inp: FinanceCalculateInput) -> dict:
    fc = _require(inp.fixed_costs, "fixed_costs")
    price = _require(inp.price_per_unit, "price_per_unit")
    vc = _require(inp.variable_cost_per_unit, "variable_cost_per_unit")
    margin = price - vc
    if margin <= 0:
        raise ValueError("Price per unit must exceed variable cost per unit")
    units = math.ceil(fc / margin)
    revenue = _r2(units * price)
    return {"metric": "breakeven", "units": units, "revenue": revenue,
            "contribution_margin": _r2(margin),
            "interpretation": f"Breakeven at {units} units (revenue {revenue}).",
            "formula": "Breakeven Units = Fixed Costs / (Price - Variable Cost)"}


def _pmt(inp: FinanceCalculateInput) -> dict:
    rate = _require(inp.rate, "rate")
    nper = int(_require(inp.nper, "nper"))
    pv = _require(inp.pv, "pv")
    fv = inp.fv or 0.0
    typ = inp.payment_type

    if rate == 0:
        payment = -(pv + fv) / nper
    else:
        pv_factor = (1 + rate) ** nper
        payment = -(pv * pv_factor + fv) * rate / (pv_factor - 1)
        if typ == 1:
            payment /= (1 + rate)

    total = _r2(payment * nper)
    interest = _r2(total + pv + fv)
    return {"metric": "pmt", "value": _r2(payment), "total_paid": total,
            "total_interest": interest,
            "interpretation": f"Payment: {_r2(payment)} per period. Total: {total}.",
            "formula": "PMT = -PV × [r(1+r)^n] / [(1+r)^n - 1]"}


def _fv(inp: FinanceCalculateInput) -> dict:
    rate = _require(inp.rate, "rate")
    nper = int(_require(inp.nper, "nper"))
    payment = _require(inp.pmt, "pmt")
    pv = inp.pv or 0.0
    typ = inp.payment_type

    if rate == 0:
        value = -(pv + payment * nper)
    else:
        pv_factor = (1 + rate) ** nper
        pmt_factor = (pv_factor - 1) / rate
        adj_pmt = payment * (1 + rate) if typ == 1 else payment
        value = -(pv * pv_factor + adj_pmt * pmt_factor)

    return {"metric": "fv", "value": _r2(value),
            "interpretation": f"Future value: {_r2(value)} after {nper} periods.",
            "formula": "FV = -PV(1+r)^n - PMT × [((1+r)^n - 1) / r]"}


def _pv_calc(inp: FinanceCalculateInput) -> dict:
    rate = _require(inp.rate, "rate")
    nper = int(_require(inp.nper, "nper"))
    payment = _require(inp.pmt, "pmt")
    fv = inp.fv or 0.0
    typ = inp.payment_type

    if rate == 0:
        value = -(fv + payment * nper)
    else:
        pv_factor = (1 + rate) ** nper
        pmt_factor = (pv_factor - 1) / rate
        adj_pmt = payment * (1 + rate) if typ == 1 else payment
        value = -(fv / pv_factor + (adj_pmt * pmt_factor) / pv_factor)

    return {"metric": "pv", "value": _r2(value),
            "interpretation": f"Present value: {_r2(value)}.",
            "formula": "PV = -FV / (1+r)^n - PMT × [1 - (1+r)^-n] / r"}


def _wacc(inp: FinanceCalculateInput) -> dict:
    equity = _require(inp.equity, "equity")
    debt_val = _require(inp.debt, "debt")
    ce = _require(inp.cost_of_equity, "cost_of_equity")
    cd = _require(inp.cost_of_debt, "cost_of_debt")
    tax = _require(inp.tax_rate, "tax_rate")

    total = equity + debt_val
    if total == 0:
        raise ValueError("Total of equity + debt must not be zero")

    ew = equity / total
    dw = debt_val / total
    value = _r2((ew * ce + dw * cd * (1 - tax)) * 100)
    return {"metric": "wacc", "value": value,
            "equity_weight": _r2(ew * 100), "debt_weight": _r2(dw * 100),
            "interpretation": f"WACC: {value}%. Equity {_r2(ew*100)}%, Debt {_r2(dw*100)}%.",
            "formula": "WACC = (E/V × Re) + (D/V × Rd × (1 - Tc))"}


def _depreciation(inp: FinanceCalculateInput) -> dict:
    cost = _require(inp.cost, "cost")
    salvage = _require(inp.salvage, "salvage")
    life = int(_require(inp.life, "life"))
    method = (inp.method or "straight-line").lower()
    period = inp.period or 1

    base = cost - salvage
    if base <= 0:
        raise ValueError("Cost must exceed salvage value")
    if life <= 0:
        raise ValueError("Life must be positive")

    if method == "straight-line":
        value = _r2(base / life)
        interp = f"Straight-line depreciation: {value} per year for {life} years."
    elif method == "declining-balance":
        rate = 2.0 / life
        book = cost
        dep = 0.0
        for p in range(1, period + 1):
            dep = min(book * rate, book - salvage)
            dep = max(dep, 0)
            book -= dep
        value = _r2(dep)
        interp = f"Double declining balance: {value} in period {period}. Book value: {_r2(book)}."
    elif method == "sum-of-years":
        soy = life * (life + 1) / 2
        remaining = life - period + 1
        if remaining < 0:
            remaining = 0
        value = _r2((remaining / soy) * base)
        interp = f"Sum-of-years depreciation: {value} in period {period}."
    else:
        raise ValueError(f"Unknown method '{method}'. Use: straight-line, declining-balance, sum-of-years")

    return {"metric": "depreciation", "value": value, "method": method,
            "interpretation": interp}


_HANDLERS: dict[str, callable] = {
    "roi": _roi,
    "npv": _npv,
    "irr": _irr,
    "breakeven": _breakeven,
    "pmt": _pmt,
    "fv": _fv,
    "pv": _pv_calc,
    "wacc": _wacc,
    "depreciation": _depreciation,
}
