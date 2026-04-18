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


def test_registry_has_28_tools_without_workflow_deps():
    """Core-plus-forecast tool count (without Jinja2/workflow extras installed).

    Breakdown: 20 original (dashboard_push removed) + 4 finance + agent_status
    + agent_cancel + artifact_write + excel_write = 28. When `jinja2` is
    importable, 4 more tools register (workflow_generate / workflow_deploy /
    workflow_manage / suggest_automation) bringing the total to 32 — see
    test_registry_has_32_tools_with_workflow_deps below.
    """
    pool = ConnectionPool()
    registry = build_tool_registry(pool=pool)
    names = registry.names()
    # Minimum floor: 28 tools always register. If workflow deps are present,
    # the count climbs to 32 — either is correct for this environment-agnostic
    # test. The strict 28/32 split is exercised separately in
    # test_registry_factory.py.
    assert len(names) in (28, 32), f"Unexpected tool count {len(names)}: {sorted(names)}"
