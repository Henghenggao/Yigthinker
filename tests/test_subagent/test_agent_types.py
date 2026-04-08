"""Tests for agent type loading from .yigthinker/agents/*.md files."""
import pytest

from yigthinker.subagent.agent_types import AgentType, load_agent_type


ANALYST_MD = """\
---
name: analyst
description: Data analysis specialist
allowed_tools:
  - sql_query
  - df_transform
  - df_profile
model: null
---

You are a data analyst. Focus on querying and transforming data.
Always provide clear explanations of your findings.
"""


FORECASTER_MD = """\
---
name: forecaster
description: Time series forecasting agent
allowed_tools:
  - forecast_timeseries
  - forecast_regression
  - forecast_evaluate
model: claude-sonnet-4-20250514
---

You are a forecasting specialist.
"""


def test_load_agent_type(tmp_path):
    """Load a valid agent type from a .yigthinker/agents/ directory."""
    agents_dir = tmp_path / ".yigthinker" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "analyst.md").write_text(ANALYST_MD, encoding="utf-8")

    result = load_agent_type("analyst", search_dirs=[agents_dir])

    assert isinstance(result, AgentType)
    assert result.name == "analyst"
    assert result.description == "Data analysis specialist"
    assert result.allowed_tools == ["sql_query", "df_transform", "df_profile"]
    assert result.model is None
    assert "data analyst" in result.system_prompt
    assert "clear explanations" in result.system_prompt


def test_agent_type_prompt(tmp_path):
    """Verify system_prompt is the Markdown body after frontmatter."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "forecaster.md").write_text(FORECASTER_MD, encoding="utf-8")

    result = load_agent_type("forecaster", search_dirs=[agents_dir])

    assert result.name == "forecaster"
    assert result.model == "claude-sonnet-4-20250514"
    assert result.system_prompt == "You are a forecasting specialist."
    # Verify that the user prompt would be appended after separator
    full_prompt = result.system_prompt + "\n\n---\n\nTask: Forecast Q4 revenue"
    assert "Task: Forecast Q4 revenue" in full_prompt


def test_agent_type_missing():
    """load_agent_type raises FileNotFoundError for nonexistent agent type."""
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        load_agent_type("nonexistent", search_dirs=[])


def test_agent_type_invalid_frontmatter(tmp_path):
    """File without --- opener raises ValueError."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "bad.md").write_text("no frontmatter here", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML frontmatter"):
        load_agent_type("bad", search_dirs=[agents_dir])


def test_agent_type_missing_name(tmp_path):
    """Frontmatter without name field raises ValueError."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    content = """\
---
description: Missing name field
allowed_tools:
  - sql_query
---

Some prompt.
"""
    (agents_dir / "noname.md").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="missing 'name'"):
        load_agent_type("noname", search_dirs=[agents_dir])


def test_agent_type_null_model(tmp_path):
    """Frontmatter with model: null results in model=None."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    content = """\
---
name: nullmodel
description: Agent with null model
model: null
---

Prompt text.
"""
    (agents_dir / "nullmodel.md").write_text(content, encoding="utf-8")

    result = load_agent_type("nullmodel", search_dirs=[agents_dir])
    assert result.model is None
    assert result.allowed_tools is None


def test_search_order(tmp_path):
    """First matching directory wins in search order."""
    dir1 = tmp_path / "project" / "agents"
    dir2 = tmp_path / "user" / "agents"
    dir1.mkdir(parents=True)
    dir2.mkdir(parents=True)

    # Same name in both dirs, different descriptions
    (dir1 / "analyst.md").write_text("""\
---
name: analyst
description: Project-level analyst
---

Project prompt.
""", encoding="utf-8")

    (dir2 / "analyst.md").write_text("""\
---
name: analyst
description: User-level analyst
---

User prompt.
""", encoding="utf-8")

    result = load_agent_type("analyst", search_dirs=[dir1, dir2])
    assert result.description == "Project-level analyst"
