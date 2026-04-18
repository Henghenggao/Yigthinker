"""Yigfinance Track B2: self-contained ar_aging.py.j2 workflow template.

ADR-011 Track B ships ``.py.j2`` templates that ``workflow_deploy``
renders into standalone Python scripts deployable to PA / UiPath / OS
cron. These scripts run WITHOUT Yigthinker in the loop — the
architect-not-executor invariant (see ADR-006 workflow templating +
2026-04-09 workflow-rpa-bridge spec §2).

AR aging is the first template shipped (matches ``/ar-aging`` command
from Track A2). Contract:

- Self-contained: no `import yigthinker` anywhere in the rendered script
- Uses only external libs (sqlalchemy, pandas, openpyxl) available via
  requirements.txt template
- Reads connection string + output dir from config.yaml at runtime,
  not hard-coded at render time
- Produces xlsx with native openpyxl chart embedded (matches
  excel_write's new embed_chart capability from Track A2)
- Returns / logs a structured status dict on completion so PA / UiPath
  can capture it
"""
from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape


# ---------------------------------------------------------------------------
# Template location + renderability
# ---------------------------------------------------------------------------

@pytest.fixture
def finance_template_dir() -> Path:
    pkg = Path(__file__).resolve().parent.parent.parent
    return pkg / "yigthinker" / "tools" / "workflow" / "templates" / "finance"


@pytest.fixture
def jinja_env(finance_template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(finance_template_dir)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        keep_trailing_newline=True,
    )


@pytest.fixture
def sample_context() -> dict:
    return {
        "workflow_name": "ar_aging_monthly",
        "description": "Monthly AR aging for the finance team",
        "connection_name": "finance",
        "ar_table": "accounts_receivable",
        "customer_col": "customer_id",
        "customer_name_col": "customer_name",
        "amount_col": "amount_due",
        "due_date_col": "due_date",
        "status_col": "status",
        "registration_date": "2026-04-18T00:00:00Z",
    }


def test_finance_templates_dir_exists(finance_template_dir):
    assert finance_template_dir.exists(), (
        f"Missing {finance_template_dir} — create it with at minimum "
        f"ar_aging.py.j2 (Track B2 first slice)"
    )
    assert finance_template_dir.is_dir()


def test_ar_aging_template_file_exists(finance_template_dir):
    assert (finance_template_dir / "ar_aging.py.j2").exists()


def test_ar_aging_template_renders_cleanly(jinja_env, sample_context):
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    # Non-trivial output — rendering didn't silently produce an empty
    # file due to a Jinja mis-scope
    assert len(rendered) > 500


def test_rendered_script_is_valid_python(jinja_env, sample_context, tmp_path):
    """Rendered output must be syntactically valid Python — otherwise
    the deployed workflow fails on first run with a SyntaxError and
    the RPA platform has no way to diagnose why."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    script_path = tmp_path / "ar_aging_test.py"
    script_path.write_text(rendered, encoding="utf-8")
    # py_compile raises PyCompileError on syntax issues
    py_compile.compile(str(script_path), doraise=True)


# ---------------------------------------------------------------------------
# Architect-not-executor invariant
# ---------------------------------------------------------------------------

def test_rendered_script_does_not_import_yigthinker(jinja_env, sample_context):
    """Hard invariant: the deployed script runs on a machine that may
    not have Yigthinker installed (PA cloud runner, UiPath robot). The
    rendered output must not ``import yigthinker`` or call into its
    public API at runtime. Docstring references to the Yigthinker brand
    are fine — they document origin, they don't couple to the module."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    # No import lines of the form "import yigthinker" / "from yigthinker"
    for line in rendered.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import yigthinker", "from yigthinker")):
            pytest.fail(f"Forbidden import found: {stripped!r}")
    # No attribute access like yigthinker.something at runtime (anywhere
    # outside comments / docstrings — we approximate "outside a string
    # literal" by just searching for the call pattern ``yigthinker.``
    # with a trailing identifier-ish char in non-comment lines).
    import re
    # Strip comments and docstrings for the runtime check
    stripped_rendered = re.sub(r'""".*?"""', "", rendered, flags=re.DOTALL)
    stripped_rendered = re.sub(r"'''.*?'''", "", stripped_rendered, flags=re.DOTALL)
    stripped_rendered = "\n".join(
        line for line in stripped_rendered.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert not re.search(r"\byigthinker\.\w+", stripped_rendered), (
        "Rendered script calls yigthinker.* at runtime — breaks the "
        "architect-not-executor invariant"
    )


def test_rendered_script_uses_only_external_libs(jinja_env, sample_context):
    """The script should pull data + produce xlsx using only external
    libraries — sqlalchemy, pandas, openpyxl. This is what
    requirements.txt.j2 will list."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    # Must import the three pillars (one of each):
    assert "sqlalchemy" in rendered or "import sqlalchemy" in rendered or "from sqlalchemy" in rendered
    assert "pandas" in rendered
    assert "openpyxl" in rendered


# ---------------------------------------------------------------------------
# Domain logic invariants — bucket semantics
# ---------------------------------------------------------------------------

def test_rendered_script_encodes_four_aging_buckets(jinja_env, sample_context):
    """The 0-30 / 31-60 / 61-90 / 90+ bucketing is the thing that makes
    this an AR aging report vs. a generic AR dump. The rendered script
    must name each bucket — ensures the template didn't drift from the
    `/ar-aging` command's recipe (see yigthinker/commands/finance/
    ar-aging.md §3)."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    for bucket in ("0-30", "31-60", "61-90", "90+"):
        assert bucket in rendered, f"Missing aging bucket label: {bucket!r}"


def test_rendered_script_references_config_keys_not_hard_coded_creds(
    jinja_env, sample_context,
):
    """Credentials must flow from config.yaml at runtime, never be
    baked into the rendered template. This keeps the same script safe
    to commit to git and to ship in deployed bundles."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    # The script loads a config file — this is the indicator that
    # runtime values aren't hard-coded
    assert "config.yaml" in rendered or "load_config" in rendered or "yaml.safe_load" in rendered
    # No accidental password-looking literals in the rendered script
    import re
    # Only check for obvious secret leaks: "password=" or "token=" with a
    # non-placeholder value. Matches e.g. `password="supersecret"` but not
    # `password = config["password"]`.
    suspect = re.findall(
        r"""(?:password|secret|token|api_key)\s*=\s*["'][A-Za-z0-9!@#$%^&*_]{8,}["']""",
        rendered,
        flags=re.IGNORECASE,
    )
    assert not suspect, f"Rendered script contains suspected hard-coded secret: {suspect!r}"


def test_rendered_script_takes_as_of_date_from_config(jinja_env, sample_context):
    """The `/ar-aging` recipe accepts an optional as-of date. The
    deployed workflow must honor whatever date the operator sets in
    config.yaml at deploy time — defaulting to today if absent."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    assert "as_of_date" in rendered
    # `datetime.now` or `date.today` is an acceptable default-today
    # implementation; either suffices
    assert "datetime.now" in rendered or "date.today" in rendered


def test_rendered_script_writes_xlsx_with_embedded_chart(jinja_env, sample_context):
    """Deliverable parity with the /ar-aging command: the deployed
    script must also produce an xlsx with a native openpyxl chart
    embedded. Not just a CSV dump."""
    template = jinja_env.get_template("ar_aging.py.j2")
    rendered = template.render(**sample_context)
    # openpyxl native chart imports
    assert "openpyxl.chart" in rendered or "BarChart" in rendered
    # The script calls wb.save / workbook.save producing an xlsx
    assert ".xlsx" in rendered
