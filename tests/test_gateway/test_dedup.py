"""Tests for Feishu event deduplicator."""
from yigthinker.presence.channels.feishu.dedup import EventDeduplicator


def test_not_duplicate_first_time(tmp_path):
    dedup = EventDeduplicator(db_path=tmp_path / "dedup.sqlite")
    assert not dedup.is_duplicate("event_001")
    dedup.close()


def test_duplicate_after_record(tmp_path):
    dedup = EventDeduplicator(db_path=tmp_path / "dedup.sqlite")
    dedup.record("event_001")
    assert dedup.is_duplicate("event_001")
    dedup.close()


def test_not_duplicate_different_id(tmp_path):
    dedup = EventDeduplicator(db_path=tmp_path / "dedup.sqlite")
    dedup.record("event_001")
    assert not dedup.is_duplicate("event_002")
    dedup.close()


def test_survives_reopen(tmp_path):
    """Deduplication state persists across restarts (SQLite-backed)."""
    db_path = tmp_path / "dedup.sqlite"

    dedup1 = EventDeduplicator(db_path=db_path)
    dedup1.record("event_001")
    dedup1.close()

    # Reopen — should still see the event
    dedup2 = EventDeduplicator(db_path=db_path)
    assert dedup2.is_duplicate("event_001")
    dedup2.close()


def test_prune_expired(tmp_path):
    import time
    dedup = EventDeduplicator(db_path=tmp_path / "dedup.sqlite", ttl_seconds=1)
    dedup.record("event_001")
    # Wait just over the TTL so the record expires
    time.sleep(1.1)
    dedup.record("event_002")  # triggers prune
    # event_001 should have been pruned
    assert not dedup.is_duplicate("event_001")
    dedup.close()
