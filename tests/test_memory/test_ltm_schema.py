"""LTM V1 schema — dormant port. Only checks importability + structure.

These schemas are NOT wired into any MemoryProvider (spec §2.2.3). They
exist so Phase 3 can adopt them for a future SqliteLtmMemoryProvider
without re-porting.
"""
from __future__ import annotations


def test_ltm_schema_imports():
    from yigthinker.memory import ltm_schema  # noqa: F401


def test_ltm_tables_defined():
    from yigthinker.memory.ltm_schema import Base, LongTermMemory

    assert Base is not None
    assert hasattr(LongTermMemory, "__tablename__")
    # Faithful to Drizzle source: "mr_long_term_memories"
    assert LongTermMemory.__tablename__ == "mr_long_term_memories"

    cols = {c.name for c in LongTermMemory.__table__.columns}
    # Core fields present in Drizzle source.
    assert "id" in cols
    assert "yigbot_id" in cols  # owner identifier in Yigcore source
    assert "organization_id" in cols
    assert "type" in cols
    assert "content" in cols
    assert "context" in cols
    assert "importance" in cols
    assert "confidence" in cols
    assert "source_blocks" in cols
    assert "created_at" in cols
    assert "last_accessed_at" in cols
    assert "access_count" in cols
    assert "status" in cols
    assert "superseded_by" in cols
    assert "updated_at" in cols
    assert "deleted_at" in cols


def test_ltm_indexes_defined():
    from yigthinker.memory.ltm_schema import LongTermMemory

    index_names = {ix.name for ix in LongTermMemory.__table__.indexes}
    # Drizzle has idx_mr_ltm_yigbot (yigbot_id, status) and idx_mr_ltm_importance.
    # The pgvector HNSW index is skipped (no SQLAlchemy equivalent).
    assert "idx_mr_ltm_yigbot" in index_names
    assert "idx_mr_ltm_importance" in index_names
