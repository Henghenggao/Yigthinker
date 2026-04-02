from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown

from yigthinker.agent import AgentLoop
from yigthinker.cli.commands import CommandRouter
from yigthinker.persistence import TranscriptWriter
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool

_console = Console()

if TYPE_CHECKING:
    from yigthinker.dashboard.server import DashboardSessionBridge


class Repl:
    def __init__(
        self,
        agent_loop: AgentLoop,
        ctx: SessionContext,
        pool: ConnectionPool,
        session_bridge: DashboardSessionBridge | None = None,
        plugin_commands: dict[str, str] | None = None,
    ) -> None:
        self._loop = agent_loop
        self._ctx = ctx
        self._commands = CommandRouter(pool=pool, extra_commands=plugin_commands)
        self._session_bridge = session_bridge
        self._transcript: TranscriptWriter | None = None
        if ctx.transcript_path:
            from pathlib import Path

            self._transcript = TranscriptWriter(Path(ctx.transcript_path))
        self._drilldown_token: str | None = None
        if self._session_bridge is not None:
            self._drilldown_token = self._session_bridge.register_session(
                ctx.session_id, self.process_input
            )

    async def process_input(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text.startswith("/"):
            result = await self._commands.handle(text, self._ctx)
            if result.handled:
                return result.output
            return f"Unknown command '{text.split()[0]}'. Type /help for commands."
        if self._transcript:
            self._transcript.append("user", text)
        response = await self._loop.run(text, self._ctx)
        if self._transcript:
            self._transcript.append("assistant", response)
        return response

    async def run_interactive(self) -> None:
        _console.print("[bold blue]Yigthinker[/] - AI financial analysis. Type /help or Ctrl+C to exit.")
        while True:
            try:
                user_input = _console.input("[bold cyan]>[/] ")
                if not user_input.strip():
                    continue
                output = await self.process_input(user_input)
                if output:
                    _console.print(Markdown(output) if output.startswith("#") else output)
            except (KeyboardInterrupt, EOFError):
                _console.print("\nGoodbye!")
                break
        if self._session_bridge is not None:
            self._session_bridge.unregister_session(self._ctx.session_id)
