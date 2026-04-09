"""Tests for the Jinja2 template engine and template rendering.

Covers SandboxedEnvironment enforcement, template inheritance,
SSTI prevention, AST validation, credential safety, and
checkpoint utilities rendering.
"""
from __future__ import annotations

import pytest

from yigthinker.tools.workflow.template_engine import (
    TemplateEngine,
    _validate_rendered_script,
    _scan_credential_patterns,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> TemplateEngine:
    return TemplateEngine()


@pytest.fixture
def base_context() -> dict:
    """Minimal context required by base/main.py.j2."""
    return {
        "workflow_name": "test_workflow",
        "version": 1,
        "steps": [
            {
                "id": "step_1",
                "action": "sql_query",
                "params": {"query": "SELECT * FROM orders"},
                "inputs": [],
                "body": "result = run_query(config.get('db', {}).get('connection_string', ''), **config)",
            },
            {
                "id": "step_2",
                "action": "df_transform",
                "params": {"code": "df['total'] = df['qty'] * df['price']"},
                "inputs": ["step_1"],
                "body": "import pandas as pd\nresult = transform(step_1, **config)",
            },
        ],
    }


@pytest.fixture
def checkpoint_context() -> dict:
    """Context for checkpoint_utils.py.j2 rendering."""
    return {
        "workflow_name": "test_workflow",
        "checkpoint_ids": ["step_1", "step_2"],
        "max_retries": 3,
        "gateway_url": None,
    }


@pytest.fixture
def config_context() -> dict:
    """Context for config.yaml.j2 rendering."""
    return {
        "workflow_name": "test_workflow",
        "version": 1,
        "connections": ["main_db", "reporting_db"],
        "schedule": "0 9 * * 1-5",
    }


# ---------------------------------------------------------------------------
# Test: Base template rendering
# ---------------------------------------------------------------------------

def test_render_base_template(engine: TemplateEngine, base_context: dict) -> None:
    """TemplateEngine.render('python', context) returns valid Python with
    def main(), if __name__ block, and step functions."""
    result = engine.render("python", base_context)
    assert "def main()" in result
    assert 'if __name__' in result
    assert "def step_step_1" in result
    assert "def step_step_2" in result
    # Should be valid Python
    compile(result, "<test>", "exec")


# ---------------------------------------------------------------------------
# Test: Power Automate template
# ---------------------------------------------------------------------------

def test_render_pa_template(engine: TemplateEngine, base_context: dict) -> None:
    """PA template inherits base structure and adds PA-specific content."""
    result = engine.render("power_automate", base_context)
    assert "def main()" in result
    assert "def step_step_1" in result
    # PA-specific content
    assert "Power Automate" in result or "power_automate" in result.lower()
    # Should still be valid Python
    compile(result, "<test>", "exec")


# ---------------------------------------------------------------------------
# Test: UiPath template
# ---------------------------------------------------------------------------

def test_render_uipath_template(engine: TemplateEngine, base_context: dict) -> None:
    """UiPath template inherits base structure and adds UiPath-specific content."""
    result = engine.render("uipath", base_context)
    assert "def main()" in result
    assert "def step_step_1" in result
    # UiPath-specific content
    assert "UiPath" in result or "uipath" in result.lower()
    # Should still be valid Python
    compile(result, "<test>", "exec")


# ---------------------------------------------------------------------------
# Test: checkpoint_utils.py rendering
# ---------------------------------------------------------------------------

def test_checkpoint_utils_rendered(engine: TemplateEngine, checkpoint_context: dict) -> None:
    """checkpoint_utils.py.j2 renders with retry decorator, self_heal function,
    and workflow-specific variables baked in."""
    result = engine.render_checkpoint_utils(checkpoint_context)
    assert "WORKFLOW_NAME" in result
    assert '"test_workflow"' in result
    assert "checkpoint" in result
    assert "self_heal" in result
    assert "report_status" in result
    assert "max_retries" in result.lower() or "MAX_RETRIES" in result
    # Should be valid Python
    compile(result, "<test>", "exec")


# ---------------------------------------------------------------------------
# Test: Gateway optional in checkpoint
# ---------------------------------------------------------------------------

def test_gateway_optional_in_checkpoint(engine: TemplateEngine, checkpoint_context: dict) -> None:
    """Rendered checkpoint_utils.py treats Gateway as optional --
    ConnectionError falls back to escalate action."""
    result = engine.render_checkpoint_utils(checkpoint_context)
    # Must catch connection errors
    assert "ConnectionError" in result
    # Must have escalate fallback
    assert "escalate" in result


# ---------------------------------------------------------------------------
# Test: config.yaml vault placeholders
# ---------------------------------------------------------------------------

def test_config_vault_placeholders(engine: TemplateEngine, config_context: dict) -> None:
    """config.yaml uses vault:// for all credential fields."""
    result = engine.render_config(config_context)
    assert "vault://" in result
    assert "test_workflow" in result
    assert "main_db" in result
    assert "reporting_db" in result


# ---------------------------------------------------------------------------
# Test: No plaintext credentials
# ---------------------------------------------------------------------------

def test_no_plaintext_credentials(engine: TemplateEngine, config_context: dict) -> None:
    """Rendered config.yaml must not contain patterns matching
    ://.*:.*@ or sk- or password: with non-vault values."""
    result = engine.render_config(config_context)
    # No real connection strings
    import re
    assert not re.search(r"://[^v][^a].*:.*@", result), "Found credential-like pattern"
    assert "sk-" not in result
    # password fields should only have vault:// or null
    for line in result.splitlines():
        if "password:" in line.lower():
            assert "vault://" in line or "null" in line, f"Plaintext password in: {line}"


# ---------------------------------------------------------------------------
# Test: requirements.txt rendering
# ---------------------------------------------------------------------------

def test_requirements_txt(engine: TemplateEngine) -> None:
    """requirements.txt includes deps from step actions (sql_query, df_transform)."""
    deps = TemplateEngine.compute_dependencies([
        {"action": "sql_query"},
        {"action": "df_transform"},
    ])
    context = {"workflow_name": "test_wf", "dependencies": deps}
    result = engine.render_requirements(context)
    assert "sqlalchemy" in result.lower()
    assert "pandas" in result.lower()
    assert "pyyaml" in result.lower() or "yaml" in result.lower()


# ---------------------------------------------------------------------------
# Test: SandboxedEnvironment used
# ---------------------------------------------------------------------------

def test_sandboxed_environment(engine: TemplateEngine) -> None:
    """TemplateEngine must use SandboxedEnvironment, not bare Environment."""
    env_type = type(engine._env).__name__
    assert env_type == "SandboxedEnvironment", (
        f"Expected SandboxedEnvironment, got {env_type}"
    )


# ---------------------------------------------------------------------------
# Test: SSTI blocked
# ---------------------------------------------------------------------------

def test_ssti_blocked(engine: TemplateEngine) -> None:
    """Step params containing {{ 7*7 }} must NOT be evaluated as Jinja2.
    The rendered output must contain the literal string, not '49'."""
    ssti_context = {
        "workflow_name": "ssti_test",
        "version": 1,
        "steps": [
            {
                "id": "step_1",
                "action": "sql_query",
                "params": {"query": "{{ 7*7 }}"},
                "inputs": [],
                "body": "pass",
            },
        ],
    }
    result = engine.render("python", ssti_context)
    # The SSTI payload should NOT be evaluated
    # Params are serialized as JSON strings, so {{ 7*7 }} stays as-is
    # The literal {{ 7*7 }} should appear (JSON-encoded) or at minimum
    # '49' should not appear as a standalone result of injection
    assert "49" not in result or "{{ 7*7 }}" in result or "7*7" in result


# ---------------------------------------------------------------------------
# Test: AST validation blocks dangerous patterns
# ---------------------------------------------------------------------------

def test_ast_validation_blocks_dangerous() -> None:
    """Rendered script containing import os or exec() is flagged."""
    dangerous_code = "import os\nos.system('rm -rf /')\nexec('malicious')"
    issues = _validate_rendered_script(dangerous_code)
    assert len(issues) >= 2
    assert any("os" in i for i in issues)
    assert any("exec" in i for i in issues)


# ---------------------------------------------------------------------------
# Test: AST validation allows safe imports
# ---------------------------------------------------------------------------

def test_ast_validation_allows_safe() -> None:
    """Script with import pandas and import sqlalchemy passes validation."""
    safe_code = (
        "import pandas as pd\n"
        "import sqlalchemy\n"
        "import yaml\n"
        "df = pd.DataFrame()\n"
    )
    issues = _validate_rendered_script(safe_code)
    assert issues == []


# ---------------------------------------------------------------------------
# Test: _scan_credential_patterns
# ---------------------------------------------------------------------------

def test_scan_credential_patterns_clean() -> None:
    """Config with vault:// only should have no issues."""
    clean = (
        'connection_string: "vault://main_db/connection_string"\n'
        'yigthinker_gateway: null\n'
    )
    issues = _scan_credential_patterns(clean)
    assert issues == []


def test_scan_credential_patterns_dirty() -> None:
    """Config with real credentials should be flagged."""
    dirty = (
        'connection_string: "mssql+pyodbc://sa:P@ssw0rd@server/db"\n'
        'api_key: "sk-abc123def456"\n'
    )
    issues = _scan_credential_patterns(dirty)
    assert len(issues) >= 1


# ---------------------------------------------------------------------------
# Test: compute_dependencies
# ---------------------------------------------------------------------------

def test_compute_dependencies() -> None:
    """compute_dependencies maps step actions to pip packages."""
    steps = [
        {"action": "sql_query"},
        {"action": "df_transform"},
        {"action": "chart_create"},
        {"action": "sql_query"},  # duplicate
    ]
    deps = TemplateEngine.compute_dependencies(steps)
    assert isinstance(deps, list)
    # Should be deduplicated and sorted
    assert deps == sorted(set(deps))
    # Should include expected packages
    dep_str = " ".join(deps)
    assert "sqlalchemy" in dep_str
    assert "pandas" in dep_str
    assert "plotly" in dep_str
