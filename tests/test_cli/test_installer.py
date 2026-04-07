from __future__ import annotations

import os
from unittest.mock import patch

from yigthinker.cli.installer import STRINGS, build_extras, detect_language


def test_detect_language_returns_en_by_default():
    with patch.dict(os.environ, {}, clear=True):
        with patch("yigthinker.cli.installer.locale.getlocale", return_value=(None, None)):
            with patch("yigthinker.cli.installer.platform.system", return_value="Linux"):
                assert detect_language() == "en"


def test_detect_language_zh_from_lang_env():
    with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}, clear=True):
        assert detect_language() == "zh"


def test_detect_language_zh_from_lc_all():
    with patch.dict(os.environ, {"LC_ALL": "zh_TW.UTF-8"}, clear=True):
        assert detect_language() == "zh"


def test_detect_language_zh_from_locale():
    with patch.dict(os.environ, {}, clear=True):
        with patch("yigthinker.cli.installer.locale.getlocale", return_value=("zh_CN", "UTF-8")):
            assert detect_language() == "zh"


def test_detect_language_zh_from_locale_chinese_string():
    with patch.dict(os.environ, {}, clear=True):
        with patch("yigthinker.cli.installer.locale.getlocale", return_value=("Chinese_China", "936")):
            assert detect_language() == "zh"


def test_detect_language_en_overrides_system():
    with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=True):
        with patch("yigthinker.cli.installer.locale.getlocale", return_value=("zh_CN", "UTF-8")):
            assert detect_language() == "en"


def test_strings_have_same_keys():
    assert set(STRINGS["en"].keys()) == set(STRINGS["zh"].keys())


def test_build_extras_local_no_platforms():
    assert build_extras(mode="local", platforms=[]) == "forecast,dashboard"


def test_build_extras_team_no_platforms():
    assert build_extras(mode="team", platforms=[]) == "forecast,dashboard,gateway,tui"


def test_build_extras_full_no_platforms():
    assert build_extras(mode="full", platforms=[]) == "forecast,dashboard,gateway,tui,feishu,teams,gchat"


def test_build_extras_local_with_feishu():
    assert build_extras(mode="local", platforms=["feishu"]) == "forecast,dashboard,feishu"


def test_build_extras_team_with_teams_and_gchat():
    assert build_extras(mode="team", platforms=["teams", "gchat"]) == "forecast,dashboard,gateway,tui,teams,gchat"


def test_build_extras_full_ignores_duplicate_platforms():
    result = build_extras(mode="full", platforms=["feishu"])
    assert result == "forecast,dashboard,gateway,tui,feishu,teams,gchat"
