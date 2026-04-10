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


# ---------------------------------------------------------------------------
# Phase 9: render_text() for non-Python templates (D-09, Pattern 1)
# ---------------------------------------------------------------------------


def test_render_text_skips_ast() -> None:
    """render_text renders non-Python templates without AST validation."""
    from yigthinker.tools.workflow.template_engine import TemplateEngine

    engine = TemplateEngine()
    # task_scheduler.xml.j2 must not explode even though it is XML (not Python)
    out = engine.render_text(
        "local/task_scheduler.xml.j2",
        {
            "workflow_name": "monthly_ar_aging",
            "description": "test",
            "python_exe": "C:\\Python311\\python.exe",
            "working_dir": "C:\\workflows\\monthly_ar_aging\\v1",
            "registration_date": "2026-04-10T00:00:00",
            "trigger": {
                "kind": "calendar_daily",
                "start_boundary": "2026-04-11T08:00:00",
            },
        },
    )
    assert "<?xml" in out
    assert 'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"' in out


def test_render_text_runs_credential_scanner() -> None:
    """render_text must reject plaintext credential patterns just like render_config."""
    from yigthinker.tools.workflow.template_engine import TemplateEngine

    engine = TemplateEngine()
    # setup_guide.md.j2 receives a context with a fake plaintext connection string
    with pytest.raises(ValueError, match="credential"):
        engine.render_text(
            "local/setup_guide.md.j2",
            {
                "workflow_name": "leak",
                "description": "postgres://admin:s3cret@db.example.com/prod",
                "schedule": "0 8 * * *",
                "working_dir": "/tmp/leak",
                "python_exe": "/usr/bin/python3",
            },
        )


def test_local_scheduler_templates() -> None:
    """All three local-mode templates render without errors for a typical workflow."""
    from yigthinker.tools.workflow.template_engine import TemplateEngine

    engine = TemplateEngine()
    ctx = {
        "workflow_name": "monthly_ar_aging",
        "description": "Monthly AR aging",
        "schedule": "0 8 5 * *",
        "python_exe": "/usr/bin/python3",
        "working_dir": "/home/u/.yigthinker/workflows/monthly_ar_aging/v1",
        "registration_date": "2026-04-10T00:00:00",
        "trigger": {
            "kind": "calendar_monthly",
            "day_of_month": 5,
            "start_boundary": "2026-05-05T08:00:00",
        },
    }
    xml = engine.render_text("local/task_scheduler.xml.j2", ctx)
    assert "<ScheduleByMonth>" in xml
    assert "<Day>5</Day>" in xml

    cron = engine.render_text("local/crontab.txt.j2", ctx)
    assert "PATH=" in cron
    assert "0 8 5 * *" in cron
    assert cron.endswith("\n")

    guide = engine.render_text("local/setup_guide.md.j2", ctx)
    assert "schtasks /create /xml" in guide
    assert "crontab crontab.txt" in guide
    assert "monthly_ar_aging" in guide


# ---------------------------------------------------------------------------
# Phase 9 Plan 02: PA + UiPath guided bundle templates (DEP-02)
# ---------------------------------------------------------------------------

import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


class TestPABundleTemplates:
    """DEP-02: Power Automate guided bundle templates."""

    @pytest.fixture
    def engine(self):
        from yigthinker.tools.workflow.template_engine import TemplateEngine
        return TemplateEngine()

    @pytest.fixture
    def pa_vars(self):
        return {
            "workflow_name": "monthly_report",
            "display_name": "Monthly Report",
            "description": "Send monthly AR aging summary",
            "cron_expression": "0 8 5 * *",
            "recurrence_frequency": "Month",
            "recurrence_interval": 1,
            "registration_date": "2026-04-15T10:00:00Z",
        }

    def test_workflow_json_shape(self, engine, pa_vars):
        content = engine.render_text("pa/workflow.json.j2", pa_vars)
        data = json.loads(content)
        # The envelope key for the display name lives under properties.
        assert data["properties"]["displayName"] == "Monthly Report"
        assert "iconUri" in data["properties"]
        # runtimeConfiguration.flowState is a string such as "Started"
        assert isinstance(
            data.get("runtimeConfiguration", {}).get("flowState"), str,
        )

    def test_api_properties_shape(self, engine, pa_vars):
        content = engine.render_text("pa/apiProperties.json.j2", pa_vars)
        data = json.loads(content)
        assert "properties" in data
        assert data["properties"]["connectionParameters"] == {}

    def test_definition_has_recurrence_trigger(self, engine, pa_vars):
        content = engine.render_text("pa/definition.json.j2", pa_vars)
        data = json.loads(content)
        trig = data["definition"]["triggers"]
        # Recurrence trigger by convention - key name can be any
        trigger_values = list(trig.values())
        assert any(
            "Recurrence" in str(v.get("type", ""))
            for v in trigger_values
        )

    def test_guided_pa_bundle(self, engine, pa_vars, tmp_path):
        """test_guided_pa_bundle - canonical test row 09-02-01."""
        from yigthinker.tools.workflow.pa_bundle import build_pa_bundle
        bundle_path = build_pa_bundle(
            workflow_name="monthly_report",
            variables=pa_vars,
            engine=engine,
            output_dir=tmp_path,
        )
        assert bundle_path.exists()
        assert bundle_path.name == "flow_import.zip"

        with zipfile.ZipFile(bundle_path) as zf:
            names = zf.namelist()
            assert "workflow.json" in names
            assert "apiProperties.json" in names
            assert (
                "Microsoft.Flow/flows/monthly_report/definition.json"
                in names
            )


class TestUiPathBundleTemplates:
    """DEP-02: UiPath guided bundle templates."""

    @pytest.fixture
    def engine(self):
        from yigthinker.tools.workflow.template_engine import TemplateEngine
        return TemplateEngine()

    @pytest.fixture
    def uipath_vars(self):
        return {
            "workflow_name": "monthly_report",
            "display_name": "Monthly Report",
            "description": "Send monthly AR aging summary",
            "python_exe": "python",
            "registration_date": "2026-04-15T10:00:00Z",
        }

    def test_project_json_shape(self, engine, uipath_vars):
        content = engine.render_text("uipath/project.json.j2", uipath_vars)
        data = json.loads(content)
        assert data["name"] == "monthly_report"
        assert data["projectVersion"] == "1.0.0"
        assert data["targetFramework"] == "Windows"
        assert data["schemaVersion"].startswith("4.")

    def test_main_xaml_is_valid_xml(self, engine, uipath_vars):
        content = engine.render_text("uipath/main.xaml.j2", uipath_vars)
        root = ET.fromstring(content)  # raises if malformed
        assert root.tag.endswith("}Activity") or root.tag == "Activity"
        children = list(root)
        assert any("Sequence" in child.tag for child in children), (
            f"Expected Sequence in Main.xaml, got children: "
            f"{[c.tag for c in children]}"
        )

    def test_uipath_reference_fixture_parses(self):
        """Sanity check: our fixture is valid XML."""
        fixture = (
            Path(__file__).parent.parent
            / "fixtures"
            / "uipath_reference"
            / "main.xaml"
        )
        assert fixture.exists()
        ET.fromstring(fixture.read_text(encoding="utf-8"))

    def test_guided_uipath_bundle(self, engine, uipath_vars, tmp_path):
        """test_guided_uipath_bundle - canonical test row 09-02-02."""
        from yigthinker.tools.workflow.uipath_bundle import build_uipath_bundle
        bundle_path = build_uipath_bundle(
            workflow_name="monthly_report",
            variables=uipath_vars,
            engine=engine,
            output_dir=tmp_path,
        )
        assert bundle_path.exists()
        assert bundle_path.name == "process_package.zip"

        with zipfile.ZipFile(bundle_path) as zf:
            names = zf.namelist()
            assert "project.json" in names
            assert "Main.xaml" in names

    def test_flow_import_zip_structure(self, engine, uipath_vars, tmp_path):
        """Sanity check: ZIP has no traversal paths or absolute paths."""
        from yigthinker.tools.workflow.uipath_bundle import build_uipath_bundle
        bundle = build_uipath_bundle(
            workflow_name="x",
            variables={**uipath_vars, "workflow_name": "x"},
            engine=engine,
            output_dir=tmp_path,
        )
        with zipfile.ZipFile(bundle) as zf:
            for name in zf.namelist():
                assert not name.startswith("/")
                assert ".." not in name
