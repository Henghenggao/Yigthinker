"""LTM V1 schema (dormant port from Yigcore Drizzle).

Spec: docs/superpowers/specs/2026-04-17-yigthinker-phase-1-design.md §2.2.3
ADR: docs/adr/005-memory-provider-interface.md

Not imported by any code path in Phase 1a. Preserved for future
SqliteLtmMemoryProvider (Phase 3).

Source: C:/Users/gaoyu/Documents/GitHub/Yigcore/packages/infra/meeting-room-db/src/schema/long-term-memories.ts (46 LOC Drizzle)

Column naming follows the Drizzle source verbatim (snake_case DB column
names, including ``yigbot_id`` as the owner identifier and the
``mr_long_term_memories`` table name).

Type-mapping caveats:
- ``embedding vector(1536)`` (pgvector) — dropped. No standard SQLAlchemy
  equivalent. When a future SQLite/Postgres provider adopts this schema,
  the embedding should be stored alongside in a dialect-appropriate type
  (BLOB for SQLite, pgvector for Postgres) and a provider-specific migration
  should add it.
- ``source_blocks jsonb`` — mapped to ``Text``. Callers must
  serialize/deserialize JSON explicitly. (SQLAlchemy's ``JSON`` type works
  against SQLite + Postgres but we keep ``Text`` here to be dialect-agnostic
  and match the "dormant port" contract.)
- ``created_at / last_accessed_at / updated_at / deleted_at`` are
  Drizzle ``bigint`` columns storing Unix ms. Ported as ``BigInteger``
  (NOT ``DateTime``) to preserve the wire format.
- The HNSW pgvector index (``idx_mr_ltm_embedding``) is skipped; pgvector
  operator classes aren't expressible in core SQLAlchemy.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Float, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for dormant memory schemas.

    Reused by :mod:`yigthinker.memory.agent_profile` so a future migration
    can create both tables against the same metadata.
    """


class LongTermMemory(Base):
    __tablename__ = "mr_long_term_memories"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="org_default"
    )
    yigbot_id: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    # jsonb in source; stored as JSON-encoded Text for dialect independence.
    source_blocks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # All timestamps are Unix ms (Drizzle `bigint({ mode: "number" })`).
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_accessed_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    superseded_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Soft-delete / sync fields added in migration 039.
    updated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("idx_mr_ltm_yigbot", "yigbot_id", "status"),
        Index("idx_mr_ltm_importance", "importance"),
    )
