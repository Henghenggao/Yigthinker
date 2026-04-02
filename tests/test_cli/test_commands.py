import pandas as pd
import pytest

from yigthinker.cli.commands import CommandRouter
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool


@pytest.fixture
def ctx():
    ctx = SessionContext()
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2], "b": [3, 4]}))
    return ctx


async def test_vars_command_lists_registry(ctx):
    router = CommandRouter(pool=ConnectionPool())
    result = await router.handle("/vars", ctx)
    assert result.handled
    assert "df1" in result.output


async def test_unknown_command_not_handled(ctx):
    router = CommandRouter(pool=ConnectionPool())
    result = await router.handle("/nonexistent", ctx)
    assert not result.handled


async def test_help_command_returns_documented_commands(ctx):
    router = CommandRouter(pool=ConnectionPool())
    result = await router.handle("/help", ctx)
    assert result.handled
    assert "/vars" in result.output
    assert "/connect" in result.output
    assert "/export" in result.output
    assert "/schedule" in result.output
    assert "/stats" in result.output
    assert "/advisor" in result.output
    assert "/voice" in result.output


async def test_advisor_command_can_toggle_status(ctx):
    router = CommandRouter(pool=ConnectionPool())
    enabled = await router.handle("/advisor gpt-4o-mini", ctx)
    disabled = await router.handle("/advisor off", ctx)
    assert enabled.handled and "gpt-4o-mini" in enabled.output
    assert disabled.handled and "disabled" in disabled.output.lower()


async def test_plugin_command_is_exposed(ctx):
    router = CommandRouter(
        pool=ConnectionPool(),
        extra_commands={"/summary": "Summarize the latest dataset."},
    )
    result = await router.handle("/summary quick", ctx)
    assert result.handled
    assert "Summarize the latest dataset." in result.output
    assert "quick" in result.output


async def test_stats_command_returns_report(ctx):
    ctx.stats.increment("sql_queries_count")
    router = CommandRouter(pool=ConnectionPool())
    result = await router.handle("/stats", ctx)
    assert result.handled
    assert "SQL queries" in result.output
