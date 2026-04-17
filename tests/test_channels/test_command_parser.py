from yigthinker.presence.channels.command_parser import parse_channel_command


def test_parse_new_no_args():
    cmd = parse_channel_command("/new")
    assert cmd is not None
    assert cmd.name == "new"
    assert cmd.args == []


def test_parse_new_with_name():
    cmd = parse_channel_command("/new q1-analysis")
    assert cmd is not None
    assert cmd.name == "new"
    assert cmd.args == ["q1-analysis"]


def test_parse_switch():
    cmd = parse_channel_command("/switch my-project")
    assert cmd is not None
    assert cmd.name == "switch"
    assert cmd.args == ["my-project"]


def test_parse_branch():
    cmd = parse_channel_command("/branch alt-path")
    assert cmd is not None
    assert cmd.name == "branch"
    assert cmd.args == ["alt-path"]


def test_parse_sessions():
    cmd = parse_channel_command("/sessions")
    assert cmd is not None
    assert cmd.name == "sessions"


def test_parse_undo():
    cmd = parse_channel_command("/undo 1")
    assert cmd is not None
    assert cmd.name == "undo"
    assert cmd.args == ["1"]


def test_parse_undo_all():
    cmd = parse_channel_command("/undo all")
    assert cmd.args == ["all"]


def test_not_a_command():
    cmd = parse_channel_command("hello how are you")
    assert cmd is None


def test_unknown_command():
    cmd = parse_channel_command("/foobar")
    assert cmd is None


def test_command_with_leading_whitespace():
    cmd = parse_channel_command("  /new test")
    assert cmd is not None
    assert cmd.name == "new"
    assert cmd.args == ["test"]
