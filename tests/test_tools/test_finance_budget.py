import json
import pytest
from yigthinker.tools.finance.finance_budget import FinanceBudgetTool
from yigthinker.session import SessionContext


@pytest.fixture
def tool():
    return FinanceBudgetTool()


@pytest.fixture
def ctx():
    return SessionContext()


async def test_budget_template_basic(tool, ctx):
    inp = tool.input_schema(
        period="monthly",
        categories=["Sales Revenue", "Marketing", "Payroll"],
    )
    result = await tool.execute(inp, ctx)
    assert not result.is_error
    data = json.loads(result.content)
    assert data["period"] == "monthly"
    assert len(data["categories"]) == 3

    # Sales Revenue should be classified as income
    sales = data["categories"][0]
    assert sales["name"] == "Sales Revenue"
    assert sales["type"] == "income"

    # Marketing and Payroll should be expense
    assert data["categories"][1]["type"] == "expense"
    assert data["categories"][2]["type"] == "expense"


async def test_budget_template_quarterly(tool, ctx):
    inp = tool.input_schema(period="quarterly", categories=["Income", "Office Rent"])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert data["period"] == "quarterly"
    assert data["categories"][0]["type"] == "income"


async def test_budget_template_empty_categories_error(tool, ctx):
    inp = tool.input_schema(period="annual", categories=[])
    result = await tool.execute(inp, ctx)
    assert result.is_error


async def test_budget_template_has_summary(tool, ctx):
    inp = tool.input_schema(period="annual", categories=["Revenue", "Costs"])
    result = await tool.execute(inp, ctx)
    data = json.loads(result.content)
    assert "summary" in data
    assert "total_income" in data["summary"]
    assert "net_cash_flow" in data["summary"]
