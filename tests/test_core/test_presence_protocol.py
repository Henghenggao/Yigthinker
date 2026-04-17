"""Tests for yigthinker.core.presence.ChannelAdapter Protocol (Phase 1b, Task C3).

Verifies:
1. ChannelAdapter is importable from yigthinker.core.presence
2. Backwards-compat shim: yigthinker.presence.channels.base re-exports ChannelAdapter
3. Protocol requires deliver_artifact method
4. All three existing adapters (Teams/Feishu/GChat) implement deliver_artifact
"""
from __future__ import annotations

import inspect

import pytest


def test_channel_adapter_importable_from_core_presence() -> None:
    """ChannelAdapter must live at yigthinker.core.presence."""
    from yigthinker.core.presence import ChannelAdapter

    assert ChannelAdapter is not None
    assert hasattr(ChannelAdapter, "deliver_artifact")


def test_backwards_compat_shim_reexports_same_protocol() -> None:
    """presence.channels.base must still expose ChannelAdapter, identical to core.presence version."""
    from yigthinker.core.presence import ChannelAdapter as _Real
    from yigthinker.presence.channels.base import ChannelAdapter as _Shim

    assert _Shim is _Real


def test_protocol_has_deliver_artifact_method() -> None:
    """deliver_artifact must be declared as an async method on the Protocol."""
    from yigthinker.core.presence import ChannelAdapter

    assert hasattr(ChannelAdapter, "deliver_artifact")
    deliver = ChannelAdapter.deliver_artifact
    # Protocol methods show up as functions; verify it's a coroutine function.
    assert inspect.iscoroutinefunction(deliver), (
        "deliver_artifact must be async"
    )


@pytest.mark.parametrize(
    "import_path,class_name",
    [
        ("yigthinker.presence.channels.teams.adapter", "TeamsAdapter"),
        ("yigthinker.presence.channels.feishu.adapter", "FeishuAdapter"),
        ("yigthinker.presence.channels.gchat.adapter", "GChatAdapter"),
    ],
)
def test_adapters_implement_deliver_artifact(import_path: str, class_name: str) -> None:
    """Every concrete adapter must implement deliver_artifact as an async method."""
    import importlib

    module = importlib.import_module(import_path)
    cls = getattr(module, class_name)
    assert hasattr(cls, "deliver_artifact"), (
        f"{class_name} missing deliver_artifact"
    )
    assert inspect.iscoroutinefunction(cls.deliver_artifact), (
        f"{class_name}.deliver_artifact must be async"
    )
