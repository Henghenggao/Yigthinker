"""Yigthinker Agent SDK — programmatic access to the agent.

Usage:
    from yigthinker import sdk

    # Single-shot
    result = await sdk.query("analyze revenue by quarter")

    # Multi-turn
    session = await sdk.create_session()
    r1 = await session.message("load data.csv")
    r2 = await session.message("show anomalies")
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from yigthinker.builder import build_app
from yigthinker.sdk.session import SDKSession
from yigthinker.session import SessionContext
from yigthinker.settings import load_settings


async def query(
    prompt: str,
    settings: dict[str, Any] | None = None,
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Run a single-shot prompt and return the response text."""
    merged = {**load_settings(), **(settings or {})}
    app = await build_app(merged, ask_fn=None)
    ctx = SessionContext(session_id=str(uuid.uuid4()), transcript_path="")
    kwargs: dict = {}
    if on_token is not None:
        kwargs["on_token"] = on_token
    return await app.agent_loop.run(prompt, ctx, **kwargs)


async def create_session(
    settings: dict[str, Any] | None = None,
) -> SDKSession:
    """Create a new persistent multi-turn session."""
    merged = {**load_settings(), **(settings or {})}
    app = await build_app(merged, ask_fn=None)
    ctx = SessionContext(session_id=str(uuid.uuid4()), transcript_path="")
    return SDKSession(agent_loop=app.agent_loop, ctx=ctx)


async def resume_session(
    session_id: str,
    settings: dict[str, Any] | None = None,
) -> SDKSession:
    """Resume an existing session by session_id (loads transcript if available)."""
    merged = {**load_settings(), **(settings or {})}
    app = await build_app(merged, ask_fn=None)
    ctx = SessionContext(session_id=session_id, transcript_path="")
    return SDKSession(agent_loop=app.agent_loop, ctx=ctx)


__all__ = ["query", "create_session", "resume_session", "SDKSession"]
