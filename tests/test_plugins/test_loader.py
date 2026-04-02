import json

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
