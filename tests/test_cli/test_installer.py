from __future__ import annotations

import os
from unittest.mock import patch

from yigthinker.presence.cli.installer import (
    DEFAULT_INSTALL_SOURCE,
    STRINGS,
    build_extras,
    build_install_requirement,
    build_manual_install_command,
    detect_language,
)


def test_detect_language_returns_en_by_default():
    with patch.dict(os.environ, {}, clear=True):
        with patch("yigthinker.presence.cli.installer.locale.getlocale", return_value=(None, None)):
            with patch("yigthinker.presence.cli.installer.platform.system", return_value="Linux"):
                assert detect_language() == "en"


def test_detect_language_zh_from_lang_env():
    with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}, clear=True):
        assert detect_language() == "zh"


def test_detect_language_zh_from_lc_all():
    with patch.dict(os.environ, {"LC_ALL": "zh_TW.UTF-8"}, clear=True):
        assert detect_language() == "zh"


def test_detect_language_zh_from_locale():
    with patch.dict(os.environ, {}, clear=True):
        with patch("yigthinker.presence.cli.installer.locale.getlocale", return_value=("zh_CN", "UTF-8")):
            assert detect_language() == "zh"


def test_detect_language_zh_from_locale_chinese_string():
    with patch.dict(os.environ, {}, clear=True):
        with patch("yigthinker.presence.cli.installer.locale.getlocale", return_value=("Chinese_China", "936")):
            assert detect_language() == "zh"


def test_detect_language_en_overrides_system():
    with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=True):
        with patch("yigthinker.presence.cli.installer.locale.getlocale", return_value=("zh_CN", "UTF-8")):
            assert detect_language() == "en"


def test_strings_have_same_keys():
    assert set(STRINGS["en"].keys()) == set(STRINGS["zh"].keys())


def test_build_extras_local_no_platforms():
    assert build_extras(mode="local", platforms=[]) == "forecast"


def test_build_extras_team_no_platforms():
    assert build_extras(mode="team", platforms=[]) == "forecast,gateway,tui"


def test_build_extras_full_no_platforms():
    assert build_extras(mode="full", platforms=[]) == "forecast,gateway,tui,feishu,teams,gchat"


def test_build_extras_local_with_feishu():
    assert build_extras(mode="local", platforms=["feishu"]) == "forecast,feishu"


def test_build_extras_team_with_teams_and_gchat():
    assert build_extras(mode="team", platforms=["teams", "gchat"]) == "forecast,gateway,tui,teams,gchat"


def test_build_extras_full_ignores_duplicate_platforms():
    result = build_extras(mode="full", platforms=["feishu"])
    assert result == "forecast,gateway,tui,feishu,teams,gchat"


def test_build_install_requirement_defaults_to_github_source():
    assert (
        build_install_requirement("forecast,gateway")
        == f"yigthinker[forecast,gateway] @ {DEFAULT_INSTALL_SOURCE}"
    )


def test_build_manual_install_command_honors_env_override():
    with patch.dict(os.environ, {"YIGTHINKER_INSTALL_SOURCE": "git+https://example.com/custom/Yigthinker.git"}, clear=False):
        assert build_manual_install_command("forecast") == (
            'uv tool install "yigthinker[forecast] @ git+https://example.com/custom/Yigthinker.git"'
        )
