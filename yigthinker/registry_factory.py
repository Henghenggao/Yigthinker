from __future__ import annotations

from yigthinker.tools.dataframe.df_load import DfLoadTool
from yigthinker.tools.dataframe.df_merge import DfMergeTool
from yigthinker.tools.dataframe.df_profile import DfProfileTool
from yigthinker.tools.dataframe.df_transform import DfTransformTool
from yigthinker.tools.exploration.explore_anomaly import ExploreAnomalyTool
from yigthinker.tools.exploration.explore_drilldown import ExploreDrilldownTool
from yigthinker.tools.exploration.explore_overview import ExploreOverviewTool
from yigthinker.tools.registry import ToolRegistry
from yigthinker.tools.reports.report_generate import ReportGenerateTool
from yigthinker.tools.reports.report_schedule import ReportScheduleTool
from yigthinker.tools.reports.report_template import ReportTemplateTool
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.tools.sql.schema_inspect import SchemaInspectTool
from yigthinker.tools.sql.sql_explain import SqlExplainTool
from yigthinker.tools.sql.sql_query import SqlQueryTool
from yigthinker.tools.visualization.chart_create import ChartCreateTool
from yigthinker.tools.visualization.chart_modify import ChartModifyTool
from yigthinker.tools.visualization.chart_recommend import ChartRecommendTool
from yigthinker.tools.agent_cancel import AgentCancelTool
from yigthinker.tools.agent_status import AgentStatusTool
from yigthinker.tools.spawn_agent import SpawnAgentTool
from yigthinker.tools.finance.finance_calculate import FinanceCalculateTool
from yigthinker.tools.finance.finance_analyze import FinanceAnalyzeTool
from yigthinker.tools.finance.finance_validate import FinanceValidateTool
from yigthinker.tools.finance.finance_budget import FinanceBudgetTool


def _register_forecast_tools(registry: ToolRegistry) -> None:
    """Register forecast tools only when their optional dependencies are installed."""
    try:
        from yigthinker.tools.forecast.forecast_evaluate import ForecastEvaluateTool
        from yigthinker.tools.forecast.forecast_regression import ForecastRegressionTool
        from yigthinker.tools.forecast.forecast_timeseries import ForecastTimeseriesTool
    except ModuleNotFoundError:
        return

    registry.register(ForecastTimeseriesTool())
    registry.register(ForecastRegressionTool())
    registry.register(ForecastEvaluateTool())


def _register_workflow_tools(
    registry: ToolRegistry,
    workflow_registry: "WorkflowRegistry",
) -> None:
    """Register workflow tools only when Jinja2 is installed."""
    try:
        from yigthinker.tools.workflow.workflow_generate import WorkflowGenerateTool
        from yigthinker.tools.workflow.workflow_deploy import WorkflowDeployTool
    except ModuleNotFoundError:
        return
    registry.register(WorkflowGenerateTool(registry=workflow_registry))
    registry.register(WorkflowDeployTool(registry=workflow_registry))


def build_tool_registry(
    pool: ConnectionPool,
    workflow_registry: "WorkflowRegistry | None" = None,
) -> ToolRegistry:
    """Register all available Yigthinker tools."""
    registry = ToolRegistry()

    registry.register(SqlQueryTool(pool=pool))
    registry.register(SqlExplainTool(pool=pool))
    registry.register(SchemaInspectTool(pool=pool))

    registry.register(DfLoadTool())
    registry.register(DfTransformTool())
    registry.register(DfProfileTool())
    registry.register(DfMergeTool())

    registry.register(ChartCreateTool())
    registry.register(ChartModifyTool())
    registry.register(ChartRecommendTool())
    registry.register(ReportGenerateTool())
    registry.register(ReportTemplateTool())
    registry.register(ReportScheduleTool())

    _register_forecast_tools(registry)

    if workflow_registry is not None:
        _register_workflow_tools(registry, workflow_registry)

    registry.register(ExploreOverviewTool())
    registry.register(ExploreDrilldownTool())
    registry.register(ExploreAnomalyTool())

    registry.register(FinanceCalculateTool())
    registry.register(FinanceAnalyzeTool())
    registry.register(FinanceValidateTool())
    registry.register(FinanceBudgetTool())

    spawn_tool = SpawnAgentTool()
    registry.register(spawn_tool)
    registry.register(AgentStatusTool())
    registry.register(AgentCancelTool())
    # Give spawn_agent a reference to the full registry for allowed_tools validation
    spawn_tool._tools = registry

    return registry
