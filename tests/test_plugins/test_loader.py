import json
from pathlib import Path

import pytest

from yigthinker.plugins.loader import PluginLoader


@pytest.fixture
def plugin_dir(tmp_path):
    plugin = tmp_path / "yigthinker-plugin-test"
    plugin.mkdir()

    meta_dir = plugin / ".yigthinker-plugin"
    meta_dir.mkdir()
    (meta_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "test-plugin",
                "version": "1.0.0",
                "description": "Test plugin",
                "author": "Test",
            }
        )
    )

    commands_dir = plugin / "commands"
    commands_dir.mkdir()
    (commands_dir / "summary.md").write_text(
        """---
description: Generate a quick summary
allowed-tools: df_profile
---

Run df_profile on the last loaded DataFrame and summarize.
"""
    )

    hooks_dir = plugin / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "hooks.json").write_text(json.dumps({"hooks": []}))

    return plugin


def test_plugin_loader_finds_manifest(plugin_dir):
    loader = PluginLoader(plugin_dirs=[plugin_dir.parent])
    plugins = loader.discover()
    assert len(plugins) == 1
    assert plugins[0].name == "test-plugin"


def test_plugin_loader_loads_commands(plugin_dir):
    loader = PluginLoader(plugin_dirs=[plugin_dir.parent])
    commands = loader.load_commands()
    assert len(commands) == 1
    assert commands[0].name == "summary"


def make_plugin(tmp_path: Path, name: str = "test-plugin", extra: dict | None = None) -> Path:
    plugin_dir = tmp_path / name
    manifest_dir = plugin_dir / ".yigthinker-plugin"
    manifest_dir.mkdir(parents=True)
    data = {"name": name, "version": "1.0.0", "description": "Test", "author": "Dev"}
    if extra:
        data.update(extra)
    (manifest_dir / "plugin.json").write_text(json.dumps(data))
    return plugin_dir


def test_manifest_reads_hooks_config_path(tmp_path):
    plugin_dir = make_plugin(tmp_path, extra={"hooks": "hooks/hooks.json"})
    hooks_path = plugin_dir / "hooks" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({"PreToolUse": []}))

    loader = PluginLoader(plugin_dirs=[tmp_path])
    manifests = loader.discover()

    assert len(manifests) == 1
    assert manifests[0].hooks_config == plugin_dir / "hooks" / "hooks.json"


def test_manifest_reads_mcp_servers(tmp_path):
    extra = {
        "mcpServers": {
            "my-server": {"transport": "sse", "url": "http://localhost:9000/sse"}
        }
    }
    make_plugin(tmp_path, extra=extra)

    loader = PluginLoader(plugin_dirs=[tmp_path])
    manifests = loader.discover()

    assert manifests[0].mcp_servers == extra["mcpServers"]


def test_manifest_reads_agents_dir(tmp_path):
    plugin_dir = make_plugin(tmp_path, extra={"agents": "agents"})
    agents_dir = plugin_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "analyst.md").write_text("---\ndescription: analyst\n---\nYou are an analyst.")

    loader = PluginLoader(plugin_dirs=[tmp_path])
    manifests = loader.discover()

    assert manifests[0].agents_dir == agents_dir


def test_load_hooks_registers_command_hooks(tmp_path):
    hooks_data = {
        "PreToolUse": [{"matcher": "sql_query", "command": "python audit.py"}]
    }
    plugin_dir = make_plugin(tmp_path, extra={"hooks": "hooks/hooks.json"})
    hooks_path = plugin_dir / "hooks" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps(hooks_data))

    loader = PluginLoader(plugin_dirs=[tmp_path])
    hooks = loader.load_hooks()

    assert len(hooks) == 1
    event_type, matcher, fn = hooks[0]
    assert event_type == "PreToolUse"
    assert matcher == "sql_query"


def test_load_mcp_configs_returns_merged_server_configs(tmp_path):
    extra = {
        "mcpServers": {
            "plugin-server": {"transport": "http", "url": "http://plugin/mcp"}
        }
    }
    make_plugin(tmp_path, extra=extra)

    loader = PluginLoader(plugin_dirs=[tmp_path])
    configs = loader.load_mcp_configs()

    assert "plugin-server" in configs
    assert configs["plugin-server"]["url"] == "http://plugin/mcp"
