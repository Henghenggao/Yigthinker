import json
import pytest
from yigthinker.tools.finance.finance_calculate import FinanceCalculateTool
from yigthinker.session import SessionContext


@pytest.fixture
def tool():
    return FinanceCalculateTool()


@pytest.fixture
def ctx():
    return SessionContext()


# ── ROI ──────────────────────────────────────────────────────────────────

async def test_roi_positive(tool, ctx):
    inp = tool.input_schema(metric="roi", gain=15000, cost=10000)
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    data = json.loads(result.content)
    assert data["metric"] == "roi"
    assert data["value"] == 50.0


async def test_roi_negative(tool, ctx):
    inp = tool.input_schema(metric="roi", gain=8000, cost=10000)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["value"] == -20.0
    assert "loss" in data["interpretation"].lower()


async def test_roi_zero_cost_error(tool, ctx):
    inp = tool.input_schema(metric="roi", gain=100, cost=0)
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── NPV ──────────────────────────────────────────────────────────────────

async def test_npv_basic(tool, ctx):
    inp = tool.input_schema(metric="npv", rate=0.1, cash_flows=[-10000, 3000, 4000, 5000, 6000])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["metric"] == "npv"
    assert data["value"] > 0  # Should be ~3889


async def test_npv_negative(tool, ctx):
    inp = tool.input_schema(metric="npv", rate=0.5, cash_flows=[-10000, 1000, 1000])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["value"] < 0


async def test_npv_empty_error(tool, ctx):
    inp = tool.input_schema(metric="npv", rate=0.1, cash_flows=[])
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── IRR ──────────────────────────────────────────────────────────────────

async def test_irr_basic(tool, ctx):
    inp = tool.input_schema(metric="irr", cash_flows=[-10000, 3000, 4000, 5000, 6000])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["metric"] == "irr"
    assert 15 < data["value"] < 30  # ~24%


async def test_irr_too_few_flows(tool, ctx):
    inp = tool.input_schema(metric="irr", cash_flows=[100])
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── Breakeven ────────────────────────────────────────────────────────────

async def test_breakeven(tool, ctx):
    inp = tool.input_schema(metric="breakeven", fixed_costs=50000,
                            price_per_unit=100, variable_cost_per_unit=60)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["units"] == 1250
    assert data["contribution_margin"] == 40.0


async def test_breakeven_negative_margin_error(tool, ctx):
    inp = tool.input_schema(metric="breakeven", fixed_costs=50000,
                            price_per_unit=50, variable_cost_per_unit=60)
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── PMT ──────────────────────────────────────────────────────────────────

async def test_pmt_basic(tool, ctx):
    inp = tool.input_schema(metric="pmt", rate=0.01, nper=36, pv=10000)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["metric"] == "pmt"
    assert data["value"] < 0  # Payments are negative convention


async def test_pmt_zero_rate(tool, ctx):
    inp = tool.input_schema(metric="pmt", rate=0, nper=10, pv=1000)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["value"] == -100.0


# ── FV ───────────────────────────────────────────────────────────────────

async def test_fv_basic(tool, ctx):
    inp = tool.input_schema(metric="fv", rate=0.01, nper=36, pmt=-100)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["metric"] == "fv"
    assert data["value"] > 3600  # Should be > sum of payments due to interest


# ── PV ───────────────────────────────────────────────────────────────────

async def test_pv_basic(tool, ctx):
    inp = tool.input_schema(metric="pv", rate=0.01, nper=36, pmt=-100)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["metric"] == "pv"
    assert data["value"] > 0


# ── WACC ─────────────────────────────────────────────────────────────────

async def test_wacc(tool, ctx):
    inp = tool.input_schema(metric="wacc", equity=600000, debt=400000,
                            cost_of_equity=0.08, cost_of_debt=0.05, tax_rate=0.25)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["metric"] == "wacc"
    assert data["equity_weight"] == 60.0
    assert data["debt_weight"] == 40.0
    # WACC = 0.6*0.08 + 0.4*0.05*0.75 = 0.048 + 0.015 = 6.3%
    assert abs(data["value"] - 6.3) < 0.1


async def test_wacc_zero_total_error(tool, ctx):
    inp = tool.input_schema(metric="wacc", equity=0, debt=0,
                            cost_of_equity=0.08, cost_of_debt=0.05, tax_rate=0.25)
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── Depreciation ─────────────────────────────────────────────────────────

async def test_depreciation_straight_line(tool, ctx):
    inp = tool.input_schema(metric="depreciation", cost=10000, salvage=1000,
                            life=5, method="straight-line")
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["value"] == 1800.0  # (10000-1000)/5


async def test_depreciation_declining_balance(tool, ctx):
    inp = tool.input_schema(metric="depreciation", cost=10000, salvage=1000,
                            life=5, method="declining-balance", period=1)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["value"] == 4000.0  # 10000 * (2/5)


async def test_depreciation_sum_of_years(tool, ctx):
    inp = tool.input_schema(metric="depreciation", cost=10000, salvage=1000,
                            life=5, method="sum-of-years", period=1)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    # SoY = 15, year 1 = 5/15 * 9000 = 3000
    assert data["value"] == 3000.0


async def test_depreciation_bad_method(tool, ctx):
    inp = tool.input_schema(metric="depreciation", cost=10000, salvage=1000,
                            life=5, method="magic")
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── IRR convergence ──────────────────────────────────────────────────────

async def test_irr_no_sign_change_error(tool, ctx):
    """All-positive cash flows have no IRR — should error, not return garbage."""
    inp = tool.input_schema(metric="irr", cash_flows=[100, 200, 300])
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "converge" in result.content.lower()


async def test_irr_multiple_sign_changes(tool, ctx):
    """Cash flows with a valid IRR should still converge normally."""
    inp = tool.input_schema(metric="irr", cash_flows=[-1000, 500, 400, 300])
    result = await tool.execute(inp, ctx)
    assert not result.is_error


# ── Depreciation period validation ──────────────────────────────────────

async def test_depreciation_period_zero_error(tool, ctx):
    """period=0 is invalid for depreciation and should error."""
    inp = tool.input_schema(metric="depreciation", cost=10000, salvage=1000,
                            life=5, method="sum-of-years", period=0)
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "period" in result.content.lower()


# ── Missing params ───────────────────────────────────────────────────────

async def test_missing_required_param(tool, ctx):
    inp = tool.input_schema(metric="roi", gain=100)  # cost missing
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "cost" in result.content.lower()
