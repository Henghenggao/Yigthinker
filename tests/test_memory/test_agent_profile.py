"""AgentProfile schema — dormant port from Yigcore core-memories.

Not wired into any runtime path. Only imports + structural checks.
"""
from __future__ import annotations


def test_agent_profile_imports():
    from yigthinker.memory import agent_profile  # noqa: F401


def test_agent_profile_table_defined():
    from yigthinker.memory.agent_profile import AgentProfile

    # Faithful to Drizzle source: "mr_core_memories"
    assert AgentProfile.__tablename__ == "mr_core_memories"

    cols = {c.name for c in AgentProfile.__table__.columns}
    # Primary key in source is yigbot_id (no separate id column).
    assert "yigbot_id" in cols
    assert "identity_role" in cols
    assert "identity_personality" in cols
    assert "identity_expertise" in cols
    assert "identity_constraints" in cols
    assert "user_relation_name" in cols
    assert "user_relation_prefs" in cols
    assert "user_relation_history" in cols
    assert "updated_at" in cols
    assert "deleted_at" in cols


def test_agent_profile_shares_base_with_ltm():
    """Both dormant schemas must share a single DeclarativeBase so a
    future Phase 3 Alembic migration can emit both tables together.
    """
    from yigthinker.memory.agent_profile import AgentProfile
    from yigthinker.memory.ltm_schema import Base, LongTermMemory

    # Same MetaData instance => same Base.
    assert AgentProfile.metadata is Base.metadata
    assert LongTermMemory.metadata is Base.metadata
    tables = set(Base.metadata.tables.keys())
    assert "mr_long_term_memories" in tables
    assert "mr_core_memories" in tables
