"""Agent profile schema (dormant port from Yigcore core-memories).

Spec: docs/superpowers/specs/2026-04-17-yigthinker-phase-1-design.md §2.2.3
ADR: docs/adr/005-memory-provider-interface.md

Not imported by core code paths in Phase 1a. Preserved so a future
AgentProfile / "core memories" provider (Phase 3+) can adopt it without
re-porting.

Source: C:/Users/gaoyu/Documents/GitHub/Yigcore/packages/infra/meeting-room-db/src/schema/core-memories.ts (15 LOC Drizzle)

Uses the shared :class:`yigthinker.memory.ltm_schema.Base` so both
dormant schemas live on a single ``MetaData`` and can be Alembic-migrated
together.

Type-mapping caveats:
- ``identity_expertise / identity_constraints / user_relation_prefs``
  are Drizzle ``jsonb`` columns. Mapped to ``Text`` here; callers
  serialize/deserialize JSON explicitly to stay dialect-agnostic.
- ``updated_at / deleted_at`` are Drizzle ``bigint`` Unix-ms fields;
  ported as ``BigInteger`` (NOT ``DateTime``) to preserve wire format.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from yigthinker.memory.ltm_schema import Base


class AgentProfile(Base):
    __tablename__ = "mr_core_memories"

    # In the Drizzle source yigbot_id is the primary key — there is no
    # separate surrogate id column.
    yigbot_id: Mapped[str] = mapped_column(Text, primary_key=True)
    identity_role: Mapped[str] = mapped_column(Text, nullable=False)
    identity_personality: Mapped[str] = mapped_column(Text, nullable=False)
    # jsonb in source; stored as JSON-encoded Text for dialect independence.
    identity_expertise: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    identity_constraints: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    user_relation_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_relation_prefs: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    user_relation_history: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Unix ms — see module docstring.
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
