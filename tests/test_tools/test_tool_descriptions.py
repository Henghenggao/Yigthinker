"""Contract tests: tool descriptions must steer the LLM toward action.

These tests enforce that artifact-producing tools include explicit
"USE ME when ..." steering language. This is part of Phase 0 fix for
the Teams Excel gap.
"""
from __future__ import annotations


def test_report_generate_description_steers_llm():
    """report_generate must have explicit 'use this for Excel/PDF/etc' cue."""
    from yigthinker.tools.reports.report_generate import ReportGenerateTool
    desc = ReportGenerateTool.description.lower()
    # Must have a strong 'use this' style steering cue
    assert "use this" in desc or "call this" in desc or "prefer this" in desc, (
        f"report_generate description must have explicit steering language. "
        f"Got: {ReportGenerateTool.description!r}"
    )
    # Must name user-facing formats
    for fmt in ("excel", "pdf"):
        assert fmt in desc, f"report_generate must mention '{fmt}' in description"


def test_df_load_description_limits_scope():
    """df_load must explicitly say it is for DATA files, not scripts."""
    from yigthinker.tools.dataframe.df_load import DfLoadTool
    desc = DfLoadTool.description.lower()
    assert "data" in desc
    assert "artifact_write" in DfLoadTool.description, (
        "df_load description must point script/text use cases to artifact_write"
    )


def test_artifact_write_description_steers_llm():
    """artifact_write must be identified as the path for scripts/text files."""
    from yigthinker.tools.artifact_write import ArtifactWriteTool
    desc = ArtifactWriteTool.description.lower()
    assert "script" in desc or "text" in desc or "file" in desc
    # Must have a 'use this for' cue
    assert "use this" in desc or "call this" in desc or "save" in desc
