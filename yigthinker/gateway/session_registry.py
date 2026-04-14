"""Session registry: maps session keys to managed sessions with lifecycle."""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yigthinker.session import SessionContext

logger = logging.getLogger(__name__)


@dataclass
class ManagedSession:
    """A gateway-managed session with concurrency guard and metadata."""

    key: str
    ctx: SessionContext
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    channel_origin: str = "cli"

    def touch(self) -> None:
        self.last_active = time.monotonic()
        self.ctx.mark_active()
        self.ctx.set_channel_origin(self.channel_origin)

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_active

    def to_info(self) -> dict[str, Any]:
        var_infos = self.ctx.vars.list()
        return {
            "key": self.key,
            "session_id": self.ctx.session_id,
            "channel_origin": self.channel_origin,
            "idle_seconds": round(self.idle_seconds(), 1),
            "message_count": len(self.ctx.messages),
            "var_count": len(var_infos),
            "vars": [
                {"name": v.name, "shape": v.shape, "dtypes": v.dtypes}
                for v in var_infos
            ],
        }


class SessionRegistry:
    """Manages the lifecycle of all gateway sessions.

    Sessions are created on demand, evicted after idle timeout, and can be
    hibernated to / restored from disk.
    """

    def __init__(
        self,
        idle_timeout: int = 3600,
        max_sessions: int = 100,
        hibernate_dir: Path | None = None,
    ) -> None:
        self._sessions: dict[str, ManagedSession] = {}
        self._idle_timeout = idle_timeout
        self._max_sessions = max_sessions
        self._hibernate_dir = _resolve_hibernate_dir(hibernate_dir)
        self._active_keys: dict[str, str] = {}  # sender_key -> active_session_key

    def get_or_create(
        self,
        key: str,
        settings: dict[str, Any],
        channel: str = "cli",
    ) -> ManagedSession:
        """Return an existing session or create a new one.

        If ``max_sessions`` is reached, the least-recently-used idle session
        is evicted first.
        """
        if key in self._sessions:
            session = self._sessions[key]
            session.channel_origin = channel or session.channel_origin
            session.touch()
            return session

        # Evict LRU idle session if at capacity
        if len(self._sessions) >= self._max_sessions:
            self._evict_lru()

        ctx = SessionContext(settings=settings, owner_id=key)
        session = ManagedSession(key=key, ctx=ctx, channel_origin=channel)
        session.ctx.set_channel_origin(channel)
        session.ctx.mark_active()
        self._sessions[key] = session
        logger.info("Created session %s (channel=%s)", key, channel)
        return session

    async def get_or_restore(
        self,
        key: str,
        settings: dict[str, Any],
        channel: str = "cli",
    ) -> ManagedSession:
        """Return an in-memory session, restore a hibernated one, or create new."""
        session = self.get(key)
        if session is not None:
            session.channel_origin = channel or session.channel_origin
            session.touch()
            return session

        restored = await self.restore(key, settings, channel=channel)
        if restored is not None:
            return restored

        return self.get_or_create(key, settings, channel)

    def get(self, key: str) -> ManagedSession | None:
        return self._sessions.get(key)

    def remove(self, key: str) -> ManagedSession | None:
        session = self._sessions.pop(key, None)
        if session:
            logger.info("Removed session %s", key)
            # Clean up any sender->key mappings that pointed to this session
            stale = [k for k, v in self._active_keys.items() if v == key]
            for k in stale:
                del self._active_keys[k]
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = sorted(self._sessions.values(), key=lambda s: s.last_active, reverse=True)
        return [s.to_info() for s in sessions]

    def list_sessions_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        """Return sessions owned by a specific user, sorted by activity."""
        sessions = sorted(
            (s for s in self._sessions.values() if s.ctx.owner_id == owner_id),
            key=lambda s: s.last_active,
            reverse=True,
        )
        return [s.to_info() for s in sessions]

    def is_owner(self, key: str, owner_id: str) -> bool:
        """Check if the given owner_id matches the session's owner."""
        session = self._sessions.get(key)
        if session is None:
            return False
        return session.ctx.owner_id == owner_id

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    async def evict_idle(self) -> int:
        """Evict sessions idle beyond ``idle_timeout``. Returns eviction count."""
        to_evict = [
            key for key, s in self._sessions.items()
            if s.idle_seconds() > self._idle_timeout and not s.lock.locked()
        ]
        evicted = 0
        for key in to_evict:
            if await self.hibernate(key):
                evicted += 1
        return evicted

    async def hibernate(self, key: str) -> bool:
        """Serialize a session to disk and remove from memory."""
        session = self._sessions.get(key)
        if not session:
            return False

        from yigthinker.gateway.hibernation import SessionHibernator

        hibernator = SessionHibernator(self._hibernate_dir)
        try:
            session.touch()
            await hibernator.save(session)
            self._sessions.pop(key, None)
            logger.info("Hibernated session %s", key)
            return True
        except Exception:
            logger.exception("Failed to hibernate session %s", key)
            return False

    async def restore(
        self,
        key: str,
        settings: dict[str, Any],
        channel: str = "cli",
    ) -> ManagedSession | None:
        """Restore a previously hibernated session from disk."""
        from yigthinker.gateway.hibernation import SessionHibernator

        hibernator = SessionHibernator(self._hibernate_dir)
        try:
            session = await hibernator.load(key, settings)
            if session:
                session.channel_origin = channel or session.channel_origin
                session.touch()
                self._sessions[key] = session
                logger.info("Restored session %s", key)
            return session
        except Exception:
            logger.exception("Failed to restore session %s", key)
            return None

    async def shutdown(self) -> None:
        """Hibernate all active sessions. Called during graceful shutdown."""
        keys = list(self._sessions.keys())
        for key in keys:
            await self.hibernate(key)
        logger.info("Shut down %d sessions", len(keys))

    def get_active_key(self, sender_key: str) -> str:
        """Return the active session key for a sender (defaults to sender_key itself)."""
        return self._active_keys.get(sender_key, sender_key)

    def set_active_key(self, sender_key: str, session_key: str) -> None:
        """Set the active session key for a sender."""
        self._active_keys[sender_key] = session_key

    def reset_session(
        self,
        key: str,
        settings: dict[str, Any],
        channel: str = "cli",
    ) -> ManagedSession:
        """Remove and recreate a session (clears all state)."""
        self.remove(key)
        return self.get_or_create(key, settings, channel)

    def _evict_lru(self) -> None:
        """Remove the least-recently-used unlocked session."""
        candidates = [
            (key, s) for key, s in self._sessions.items()
            if not s.lock.locked()
        ]
        if not candidates:
            logger.warning("All %d sessions are locked; cannot evict", len(self._sessions))
            return

        lru_key, lru_session = min(candidates, key=lambda x: x[1].last_active)
        self._sessions.pop(lru_key, None)
        self._schedule_hibernate(lru_session)
        logger.warning("LRU-evicted session %s (at capacity %d)", lru_key, self._max_sessions)

    def _schedule_hibernate(self, session: ManagedSession) -> None:
        from yigthinker.gateway.hibernation import SessionHibernator

        hibernator = SessionHibernator(self._hibernate_dir)
        session.touch()

        async def _save() -> None:
            try:
                await hibernator.save(session)
            except Exception:
                logger.exception("Failed to hibernate LRU-evicted session %s", session.key)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_save())
        else:
            loop.create_task(_save())


def _resolve_hibernate_dir(hibernate_dir: Path | None) -> Path:
    """Choose a writable hibernation directory, falling back to temp if needed."""
    candidates = []
    if hibernate_dir is not None:
        candidates.append(Path(hibernate_dir).expanduser())
    else:
        candidates.append((Path.home() / ".yigthinker" / "hibernate").expanduser())
        candidates.append(Path(tempfile.gettempdir()) / "yigthinker" / "hibernate")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            logger.warning("Hibernate dir not writable: %s", candidate)

    raise OSError("No writable hibernate directory available")
