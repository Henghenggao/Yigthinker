# tests/test_settings.py
import json
from pathlib import Path
import pytest
from yigthinker.settings import DEFAULT_SETTINGS, _deep_merge, has_api_key, load_settings

def test_deep_merge_simple():
    result = _deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert result == {"a": 1, "b": 3, "c": 4}

def test_deep_merge_nested():
    base = {"permissions": {"allow": ["a"], "deny": []}}
    override = {"permissions": {"allow": ["b"]}}
    result = _deep_merge(base, override)
    assert result["permissions"]["allow"] == ["b"]
    assert result["permissions"]["deny"] == []  # preserved from base

def test_load_settings_returns_defaults_when_no_files(tmp_path):
    settings = load_settings(project_dir=tmp_path, user_dir=tmp_path)
    assert settings["model"] == DEFAULT_SETTINGS["model"]
    assert "permissions" in settings

def test_load_settings_project_overrides_defaults(tmp_path):
    project_settings = {"model": "gpt-4o", "permissions": {"allow": ["chart_create"]}}
    (tmp_path / ".yigthinker").mkdir()
    (tmp_path / ".yigthinker" / "settings.json").write_text(json.dumps(project_settings))
    settings = load_settings(project_dir=tmp_path, user_dir=tmp_path)
    assert settings["model"] == "gpt-4o"
    assert settings["permissions"]["allow"] == ["chart_create"]
    assert "deny" in settings["permissions"]  # deep merge: deny from defaults preserved


def test_default_settings_include_gateway_and_channels():
    assert "gateway" in DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["gateway"]["port"] == 8766
    assert "channels" in DEFAULT_SETTINGS
    assert {"feishu", "teams", "gchat"} <= set(DEFAULT_SETTINGS["channels"])


def test_has_api_key_for_ollama():
    assert has_api_key({"model": "ollama/llama3.1"})


def test_default_allow_includes_readonly_tools():
    expected = [
        "df_load",
        "df_profile",
        "df_merge",
        "schema_inspect",
        "explore_overview",
        "explore_drilldown",
        "explore_anomaly",
        "chart_create",
        "chart_modify",
        "chart_recommend",
        "forecast_timeseries",
        "forecast_regression",
        "forecast_evaluate",
        "finance_calculate",
        "finance_analyze",
        "finance_validate",
    ]
    allow_list = DEFAULT_SETTINGS["permissions"]["allow"]
    for tool_name in expected:
        assert tool_name in allow_list, f"{tool_name} should be in default allow list"
    assert len(allow_list) == 16


def test_default_allow_excludes_write_tools():
    allow_list = DEFAULT_SETTINGS["permissions"]["allow"]
    write_tools = ["sql_query", "df_transform", "workflow_deploy", "spawn_agent"]
    for tool_name in write_tools:
        assert tool_name not in allow_list, f"{tool_name} should NOT be in default allow list"
