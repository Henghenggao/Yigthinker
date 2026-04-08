import json
import pytest
from yigthinker.tools.finance.finance_analyze import FinanceAnalyzeTool
from yigthinker.session import SessionContext


@pytest.fixture
def tool():
    return FinanceAnalyzeTool()


@pytest.fixture
def ctx():
    return SessionContext()


# ── Ratios ───────────────────────────────────────────────────────────────

async def test_ratios_profitability(tool, ctx):
    inp = tool.input_schema(
        analysis_type="ratios",
        revenue=1_000_000, costs=600_000, net_income=250_000,
        assets=2_000_000, equity=1_200_000,
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    prof = data["results"]["profitability"]
    assert prof["gross_margin"] == 40.0
    assert prof["net_margin"] == 25.0
    assert prof["return_on_assets"] == 12.5
    assert prof["return_on_equity"] == 20.83


async def test_ratios_liquidity(tool, ctx):
    inp = tool.input_schema(
        analysis_type="ratios",
        current_assets=500_000, current_liabilities=300_000, inventory=100_000,
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    liq = data["results"]["liquidity"]
    assert liq["current_ratio"] == 1.67
    assert liq["quick_ratio"] == 1.33


async def test_ratios_leverage(tool, ctx):
    inp = tool.input_schema(
        analysis_type="ratios",
        liabilities=800_000, equity=1_200_000, assets=2_000_000,
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    lev = data["results"]["leverage"]
    assert lev["debt_to_equity"] == 0.67
    assert lev["debt_to_assets"] == 40.0


async def test_ratios_insufficient_data(tool, ctx):
    inp = tool.input_schema(analysis_type="ratios")
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── Trends ───────────────────────────────────────────────────────────────

async def test_trends_upward(tool, ctx):
    inp = tool.input_schema(analysis_type="trends", values=[100, 110, 121, 133])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["direction"] == "upward"
    assert data["average_change_pct"] > 9


async def test_trends_stable(tool, ctx):
    inp = tool.input_schema(analysis_type="trends", values=[100, 100, 100])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["direction"] == "stable"


async def test_trends_with_labels(tool, ctx):
    inp = tool.input_schema(analysis_type="trends",
                            values=[100, 120, 130],
                            labels=["Jan", "Feb", "Mar"])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["periods"][0]["label"] == "Feb"


async def test_trends_too_few_error(tool, ctx):
    inp = tool.input_schema(analysis_type="trends", values=[100])
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── Variance ─────────────────────────────────────────────────────────────

async def test_variance_basic(tool, ctx):
    inp = tool.input_schema(
        analysis_type="variance",
        actual=[110, 90, 100],
        budget=[100, 100, 100],
        categories=["Sales", "Marketing", "Ops"],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert len(data["variances"]) == 3
    assert data["variances"][0]["status"] == "favorable"
    assert data["variances"][1]["status"] == "unfavorable"
    assert data["variances"][2]["status"] == "neutral"
    assert data["total_variance"] == 0.0


async def test_variance_mismatched_error(tool, ctx):
    inp = tool.input_schema(analysis_type="variance", actual=[1, 2], budget=[1])
    result = await tool.execute(inp, ctx)
    assert result.is_error


# ── Scenario ─────────────────────────────────────────────────────────────

async def test_scenario_basic(tool, ctx):
    inp = tool.input_schema(
        analysis_type="scenario",
        base_case={"revenue": 1000, "costs": 600, "tax_rate": 0.2},
        scenarios=[
            {"name": "optimistic", "assumptions": {"revenue": 1200}},
            {"name": "pessimistic", "assumptions": {"revenue": 800}},
        ],
        output_metrics=["net_income"],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["comparison"]["best_case"] == "optimistic"
    assert data["comparison"]["worst_case"] == "pessimistic"
    opt = next(s for s in data["scenarios"] if s["name"] == "optimistic")
    assert opt["outputs"]["revenue"] == 1200


async def test_scenario_with_probabilities(tool, ctx):
    inp = tool.input_schema(
        analysis_type="scenario",
        base_case={"revenue": 1000, "costs": 600},
        scenarios=[
            {"name": "up", "assumptions": {"revenue": 1200}, "probability": 0.3},
            {"name": "base", "assumptions": {"revenue": 1000}, "probability": 0.5},
            {"name": "down", "assumptions": {"revenue": 800}, "probability": 0.2},
        ],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert "probability_weighted" in data["comparison"]


async def test_scenario_missing_data_error(tool, ctx):
    inp = tool.input_schema(analysis_type="scenario")
    result = await tool.execute(inp, ctx)
    assert result.is_error


async def test_scenario_partial_probabilities_error(tool, ctx):
    """If some scenarios have probability but not all, should error."""
    inp = tool.input_schema(
        analysis_type="scenario",
        base_case={"revenue": 1000, "costs": 600},
        scenarios=[
            {"name": "up", "assumptions": {"revenue": 1200}, "probability": 0.5},
            {"name": "down", "assumptions": {"revenue": 800}},
        ],
    )
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "probability" in result.content.lower()


async def test_scenario_bad_probability_sum_error(tool, ctx):
    """Probabilities that don't sum to 1.0 should error."""
    inp = tool.input_schema(
        analysis_type="scenario",
        base_case={"revenue": 1000, "costs": 600},
        scenarios=[
            {"name": "up", "assumptions": {"revenue": 1200}, "probability": 0.5},
            {"name": "down", "assumptions": {"revenue": 800}, "probability": 0.3},
        ],
    )
    result = await tool.execute(inp, ctx)
    assert result.is_error
    assert "sum to 1.0" in result.content


# ── Sensitivity ──────────────────────────────────────────────────────────

async def test_sensitivity_basic(tool, ctx):
    inp = tool.input_schema(analysis_type="sensitivity", revenue=1_000_000, costs=700_000)
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["margin"] == 300_000
    assert len(data["insights"]) == 3


async def test_sensitivity_missing_data_error(tool, ctx):
    inp = tool.input_schema(analysis_type="sensitivity", revenue=1_000_000)
    result = await tool.execute(inp, ctx)
    assert result.is_error
