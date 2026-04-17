from yigthinker.presence.channels.base import ChannelAdapter
from yigthinker.session import QuotedMessage  # noqa: F401


def test_channel_adapter_extract_quoted_messages_protocol_exists():
    # Protocol signature existence check
    assert hasattr(ChannelAdapter, "extract_quoted_messages")
