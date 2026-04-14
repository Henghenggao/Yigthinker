from __future__ import annotations

from typing import Callable

from yigthinker.agent import AgentLoop
from yigthinker.session import SessionContext


class SDKSession:
    """Programmatic multi-turn agent session.

    Usage:
        session = await create_session()
        result = await session.message("load data.csv")
        result2 = await session.message("show top 10 rows")
    """

    def __init__(self, agent_loop: AgentLoop, ctx: SessionContext) -> None:
        self._loop = agent_loop
        self._ctx = ctx

    @property
    def session_id(self) -> str:
        return self._ctx.session_id

    async def message(
        self,
        text: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Send a message and return the assistant's response."""
        kwargs: dict = {}
        if on_token is not None:
            kwargs["on_token"] = on_token
        return await self._loop.run(text, self._ctx, **kwargs)

    def list_vars(self):
        """Return summary of DataFrames currently in the variable registry."""
        return self._ctx.vars.list()
