from yigthinker.session import SessionContext, QuotedMessage, MessageIdMap


def test_session_has_message_id_map():
    ctx = SessionContext()
    assert isinstance(ctx.message_id_map, MessageIdMap)


def test_message_id_map_record_and_get():
    m = MessageIdMap()
    m.record("platform-123", 7)
    assert m.get_history_index("platform-123") == 7


def test_message_id_map_unknown_returns_none():
    m = MessageIdMap()
    assert m.get_history_index("nonexistent") is None


def test_quoted_message_defaults():
    q = QuotedMessage(original_id="x", original_text="hello")
    assert q.original_role == ""
    assert q.history_index is None


def test_quoted_message_full_fields():
    q = QuotedMessage(
        original_id="x",
        original_text="hi",
        original_role="assistant",
        history_index=3,
    )
    assert q.original_role == "assistant"
    assert q.history_index == 3


def test_channel_adapter_extract_quoted_messages_exists():
    from yigthinker.channels.base import ChannelAdapter
    assert hasattr(ChannelAdapter, "extract_quoted_messages")
