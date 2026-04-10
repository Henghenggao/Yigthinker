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


class TestWorkflowManageRegistration:
    """Phase 9 Plan 03: workflow_manage registered under the same workflow gate."""

    def test_workflow_manage_registered_when_gate_enabled(self, tmp_path):
        """workflow_manage is registered when a WorkflowRegistry is provided."""
        from yigthinker.tools.workflow.registry import WorkflowRegistry

        pool = ConnectionPool()
        wf_reg = WorkflowRegistry(base_dir=tmp_path / "wf_registry")
        registry = build_tool_registry(pool=pool, workflow_registry=wf_reg)
        names = registry.names()
        assert "workflow_manage" in names
        # Sanity check: all 3 workflow tools register together behind one gate
        assert "workflow_generate" in names
        assert "workflow_deploy" in names

    def test_workflow_manage_not_registered_when_gate_disabled(self):
        """No workflow tools when workflow_registry is not supplied (gate off)."""
        pool = ConnectionPool()
        registry = build_tool_registry(pool=pool)
        names = registry.names()
        assert "workflow_manage" not in names
        assert "workflow_generate" not in names
        assert "workflow_deploy" not in names
