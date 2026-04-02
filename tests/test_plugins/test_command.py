import pytest

from yigthinker.plugins.command import load_commands_from_dir


@pytest.fixture
def commands_dir(tmp_path):
    cmd = tmp_path / "commands"
    cmd.mkdir()
    (cmd / "connect.md").write_text(
        """---
description: Switch active data connection
allowed-tools: schema_inspect
argument-hint: <connection-name>
---

List available connections from the project's .yigthinker/settings.json.
If the user specified a connection name, switch to it and run schema_inspect.
"""
    )
    (cmd / "not_a_command.txt").write_text("ignored")
    return cmd


def test_load_commands_finds_md_files(commands_dir):
    commands = load_commands_from_dir(commands_dir)
    assert len(commands) == 1
    assert commands[0].name == "connect"


def test_command_parses_frontmatter(commands_dir):
    commands = load_commands_from_dir(commands_dir)
    cmd = commands[0]
    assert cmd.description == "Switch active data connection"
    assert "schema_inspect" in cmd.allowed_tools
    assert cmd.argument_hint == "<connection-name>"


def test_command_body_is_prompt(commands_dir):
    commands = load_commands_from_dir(commands_dir)
    cmd = commands[0]
    assert "connections" in cmd.body
    assert "schema_inspect" in cmd.body
