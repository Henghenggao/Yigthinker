import json
import pytest
from yigthinker.tools.finance.finance_validate import FinanceValidateTool
from yigthinker.session import SessionContext


@pytest.fixture
def tool():
    return FinanceValidateTool()


@pytest.fixture
def ctx():
    return SessionContext()


# ── Validation ───────────────────────────────────────────────────────────

async def test_validate_all_pass(tool, ctx):
    inp = tool.input_schema(
        action="validate",
        data={"revenue": 1_000_000, "costs": 600_000},
        rules=[
            {"field": "revenue", "required": True, "type": "positive"},
            {"field": "costs", "required": True, "type": "positive"},
        ],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["is_valid"]
    assert data["quality"]["completeness"] == 1.0


async def test_validate_missing_required(tool, ctx):
    inp = tool.input_schema(
        action="validate",
        data={"revenue": 1_000_000},
        rules=[
            {"field": "revenue", "required": True},
            {"field": "costs", "required": True},
        ],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert not data["is_valid"]
    assert data["quality"]["completeness"] == 0.5


async def test_validate_range_check(tool, ctx):
    inp = tool.input_schema(
        action="validate",
        data={"margin": 150},
        rules=[{"field": "margin", "type": "percentage"}],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert len(data["warnings"]) > 0


async def test_validate_accounting_equation(tool, ctx):
    inp = tool.input_schema(
        action="validate",
        data={"assets": 1000, "liabilities": 300, "equity": 500},  # 1000 != 300 + 500 = 800
        rules=[],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert not data["is_valid"]
    assert any("accounting" in e["field"] for e in data["errors"])


async def test_validate_cost_ratio_warning(tool, ctx):
    inp = tool.input_schema(
        action="validate",
        data={"revenue": 100, "costs": 95},
        rules=[],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert any("cost ratio" in w["message"].lower() for w in data["warnings"])


# ── Anomaly Detection ────────────────────────────────────────────────────

async def test_detect_anomalies_zscore(tool, ctx):
    inp = tool.input_schema(
        action="detect_anomalies",
        values=[10, 11, 12, 10, 11, 100],  # 100 is an outlier
        method="zscore",
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert len(data["anomalies"]) >= 1
    assert data["anomalies"][0]["value"] == 100


async def test_detect_anomalies_iqr(tool, ctx):
    inp = tool.input_schema(
        action="detect_anomalies",
        values=[10, 11, 12, 10, 11, 100],
        method="iqr",
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert len(data["anomalies"]) >= 1


async def test_detect_anomalies_with_labels(tool, ctx):
    inp = tool.input_schema(
        action="detect_anomalies",
        values=[10, 11, 12, 10, 11, 100],
        labels=["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        method="both",
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert any(a.get("label") == "Jun" for a in data["anomalies"])


async def test_detect_anomalies_no_outliers(tool, ctx):
    inp = tool.input_schema(
        action="detect_anomalies",
        values=[10, 11, 10, 11, 10],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert len(data["anomalies"]) == 0


async def test_detect_anomalies_statistics(tool, ctx):
    inp = tool.input_schema(
        action="detect_anomalies",
        values=[10, 20, 30],
    )
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    stats = data["statistics"]
    assert stats["mean"] == 20.0
    assert stats["median"] == 20.0
    assert stats["q1"] is not None


async def test_detect_anomalies_too_few_error(tool, ctx):
    inp = tool.input_schema(action="detect_anomalies", values=[1, 2])
    result = await tool.execute(inp, ctx)
    assert result.is_error
