"""Drift guard: MCP package identifier names in workflow tools.

Per D-26, this test ensures the legacy identifiers that existed in Phase 9/10
never come back. It is a regex-based scan -- it does NOT import the
yigthinker_mcp_uipath package (D-15 architect-not-executor invariant).

Per D-07, suggest_automation.py is pinned: line ~168 must contain
`importlib.util.find_spec("yigthinker_mcp_uipath")`. The
test_suggest_automation_pinned_to_canonical_identifier test below asserts
this invariant so that future edits cannot silently regress it.

If this test fails after editing workflow tools:
  1. Check if you reintroduced 'yigthinker_uipath_mcp' (underscore-swapped
     legacy name) or 'uipath_publish_package' (legacy tool name) or the
     'pip install yigthinker[uipath-mcp]' hint.
  2. The canonical names are:
       package:      yigthinker_mcp_uipath   (module name)
       distribution: yigthinker-mcp-uipath   (PyPI/pip name)
       extra:        yigthinker[rpa-uipath]
       deploy tool:  ui_deploy_process
"""
from __future__ import annotations

import re
from pathlib import Path


WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "yigthinker" / "tools" / "workflow"

LEGACY_PATTERNS: dict[str, str] = {
    # pattern -> human-readable reason
    r"yigthinker_uipath_mcp": "legacy underscore-swapped package name (should be yigthinker_mcp_uipath)",
    r"uipath_publish_package": "legacy single tool name (should be ui_deploy_process or one of the 5 ui_* tools)",
    r"yigthinker\[uipath-mcp\]": "legacy pip extra name (should be yigthinker[rpa-uipath])",
}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        # Skip __pycache__ etc.
        if "__pycache__" in path.parts:
            continue
        yield path


def test_no_legacy_uipath_identifiers_in_workflow_tools() -> None:
    """No legacy UiPath MCP identifiers should appear in workflow tools code."""
    assert WORKFLOW_DIR.is_dir(), f"expected workflow dir at {WORKFLOW_DIR}"
    hits: list[str] = []
    for file in _iter_python_files(WORKFLOW_DIR):
        text = file.read_text(encoding="utf-8")
        for pattern, reason in LEGACY_PATTERNS.items():
            if re.search(pattern, text):
                hits.append(f"{file.relative_to(WORKFLOW_DIR.parents[2])}: {pattern} -- {reason}")
    assert not hits, "Legacy UiPath MCP identifiers found:\n  " + "\n  ".join(hits)


def test_canonical_uipath_identifiers_present_in_mcp_detection() -> None:
    """The canonical names must appear in mcp_detection.py after drift cleanup."""
    detection = (WORKFLOW_DIR / "mcp_detection.py").read_text(encoding="utf-8")
    assert "yigthinker_mcp_uipath" in detection, "canonical package name missing"
    assert "ui_deploy_process" in detection, "canonical suggested_tool missing"
    assert "pip install yigthinker[rpa-uipath]" in detection, "canonical install hint missing"


def test_suggest_automation_pinned_to_canonical_identifier() -> None:
    """D-07 invariant: suggest_automation.py uses the canonical module name.

    Per D-07 (11-CONTEXT.md), `yigthinker/tools/workflow/suggest_automation.py`
    already contains `importlib.util.find_spec("yigthinker_mcp_uipath")` at
    line ~168. Plan 11-07 must NOT edit this file, and this test pins the
    invariant so future edits cannot silently regress it.

    Note: the file legitimately contains more than one canonical reference
    (one in a module docstring listing both MCP packages, one in the actual
    find_spec call). We assert >= 1 canonical reference and require the
    exact find_spec call shape to be present, not a specific count.
    """
    target = WORKFLOW_DIR / "suggest_automation.py"
    assert target.is_file(), f"expected {target} to exist"
    text = target.read_text(encoding="utf-8")

    # At least one reference to the canonical module name must remain.
    canonical_hits = len(re.findall(r"yigthinker_mcp_uipath", text))
    assert canonical_hits >= 1, (
        f"suggest_automation.py must reference 'yigthinker_mcp_uipath' at least once; "
        f"found {canonical_hits}"
    )

    # Zero references to the legacy underscore-swapped name.
    legacy_hits = len(re.findall(r"yigthinker_uipath_mcp", text))
    assert legacy_hits == 0, (
        f"suggest_automation.py must not contain the legacy name 'yigthinker_uipath_mcp'; "
        f"found {legacy_hits}"
    )

    # The exact find_spec call shape must be present (not just the bare string in a comment).
    assert 'importlib.util.find_spec("yigthinker_mcp_uipath")' in text, (
        "expected `importlib.util.find_spec(\"yigthinker_mcp_uipath\")` call in "
        "suggest_automation.py (D-07 invariant)"
    )
