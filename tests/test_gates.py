import os
import pytest
from unittest.mock import patch
from yigthinker.gates import gate


def test_gate_returns_default_when_not_configured():
    assert gate("nonexistent_gate", default=False) is False
    assert gate("nonexistent_gate", default=True) is True


def test_env_var_override_wins():
    with patch.dict(os.environ, {"YIGTHINKER_GATE_SPECULATION": "1"}):
        assert gate("speculation", default=False) is True
    with patch.dict(os.environ, {"YIGTHINKER_GATE_SPECULATION": "0"}):
        assert gate("speculation", default=True) is False


def test_settings_override():
    settings = {"gates": {"advisor": True}}
    assert gate("advisor", default=False, settings=settings) is True


def test_env_var_beats_settings():
    settings = {"gates": {"speculation": False}}
    with patch.dict(os.environ, {"YIGTHINKER_GATE_SPECULATION": "1"}):
        assert gate("speculation", default=False, settings=settings) is True
