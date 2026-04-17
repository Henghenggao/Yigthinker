"""Backwards-compat shim — ChannelAdapter lives in yigthinker.core.presence as of Phase 1b."""
from yigthinker.core.presence import ChannelAdapter  # noqa: F401

__all__ = ["ChannelAdapter"]
