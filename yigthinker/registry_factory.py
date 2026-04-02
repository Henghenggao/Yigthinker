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
from yigthinker.tools.spawn_agent import SpawnAgentTool
from yigthinker.tools.visualization.dashboard_push import DashboardPushTool


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


def build_tool_registry(pool: ConnectionPool) -> ToolRegistry:
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
    registry.register(DashboardPushTool())

    registry.register(ReportGenerateTool())
    registry.register(ReportTemplateTool())
    registry.register(ReportScheduleTool())

    _register_forecast_tools(registry)

    registry.register(ExploreOverviewTool())
    registry.register(ExploreDrilldownTool())
    registry.register(ExploreAnomalyTool())

    registry.register(SpawnAgentTool())

    return registry
