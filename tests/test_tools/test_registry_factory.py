from yigthinker.registry_factory import build_tool_registry
from yigthinker.tools.sql.connection import ConnectionPool


def test_all_phase2_tools_registered():
    pool = ConnectionPool()
    registry = build_tool_registry(pool=pool)
    names = registry.names()
    expected = [
        "sql_query", "sql_explain", "schema_inspect",
        "df_load", "df_transform", "df_profile", "df_merge",
    ]
    for name in expected:
        assert name in names, f"Tool '{name}' not registered"


def test_registry_exports_valid_schemas():
    pool = ConnectionPool()
    registry = build_tool_registry(pool=pool)
    schemas = registry.export_schemas()
    assert len(schemas) == 26  # 20 original (dashboard_push removed) + 4 finance + agent_status + agent_cancel
    for schema in schemas:
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema


def test_workflow_deploy_registered(tmp_path):
    """workflow_deploy must be registered alongside workflow_generate under the same gate."""
    from yigthinker.tools.workflow.registry import WorkflowRegistry

    pool = ConnectionPool()
    wf_reg = WorkflowRegistry(base_dir=tmp_path / "wf_registry")
    registry = build_tool_registry(pool=pool, workflow_registry=wf_reg)
    names = registry.names()
    assert "workflow_generate" in names
    assert "workflow_deploy" in names
