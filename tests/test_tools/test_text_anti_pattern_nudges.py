"""Tool description nudges that steer the LLM away from the text-in-DataFrame
anti-pattern observed in quick-260416-j3y.

When the agent is asked for a custom Python/SQL script or a markdown doc, there
must be ONE obvious tool (`artifact_write`). To prevent drift, the descriptions
of df_load / df_transform / workflow_generate must reference artifact_write as
the correct alternative.
"""
from __future__ import annotations

from yigthinker.tools.dataframe.df_load import DfLoadTool
from yigthinker.tools.dataframe.df_transform import DfTransformTool
from yigthinker.tools.workflow.workflow_generate import WorkflowGenerateTool


def test_df_load_description_mentions_artifact_write():
    desc = DfLoadTool.description
    # Must still describe the core capability
    assert "Load data" in desc
    # Must explicitly redirect text/code/config loads to artifact_write
    assert "artifact_write" in desc
    assert "source code" in desc.lower() or "free-form text" in desc.lower()


def test_df_transform_description_warns_against_storing_scripts():
    desc = DfTransformTool.description
    # Core capability still described
    assert "Pandas" in desc or "pandas" in desc
    # Anti-pattern warning present
    assert "artifact_write" in desc
    assert "script" in desc.lower() or "free-form text" in desc.lower()


def test_workflow_generate_description_redirects_one_off_scripts():
    desc = WorkflowGenerateTool.description
    assert "workflow" in desc.lower()
    assert "artifact_write" in desc
    # One-off / custom-format guidance is the actual root-cause fix
    assert "one-off" in desc.lower() or "openpyxl" in desc.lower()
