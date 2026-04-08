from yigthinker.registry_factory import build_tool_registry
from yigthinker.tools.sql.connection import ConnectionPool


def test_all_phase3_tools_registered():
    pool = ConnectionPool()
    registry = build_tool_registry(pool=pool)
    names = registry.names()
    expected = [
        # Phase 2
        "sql_query", "sql_explain", "schema_inspect",
        "df_load", "df_transform", "df_profile", "df_merge",
        # Phase 3
        "chart_create", "chart_modify", "chart_recommend",
        "report_generate", "report_template", "report_schedule",
        "forecast_timeseries", "forecast_regression", "forecast_evaluate",
        "explore_overview", "explore_drilldown", "explore_anomaly",
        # Finance
        "finance_calculate", "finance_analyze", "finance_validate", "finance_budget",
    ]
    for name in expected:
        assert name in names, f"Tool '{name}' not registered"


def test_registry_has_20_tools():
    pool = ConnectionPool()
    registry = build_tool_registry(pool=pool)
    assert len(registry.names()) == 26  # 20 original (dashboard_push removed) + 4 finance + agent_status + agent_cancel
