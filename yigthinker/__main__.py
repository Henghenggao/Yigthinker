from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

import typer
from rich.console import Console

app = typer.Typer(help="Yigthinker - AI-powered financial analysis agent")
console = Console()


def _default_transcript_path() -> Path:
    sessions_dir = Path.home() / ".yigthinker" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return sessions_dir / f"session-{timestamp}-{uuid.uuid4().hex[:8]}.jsonl"


def _hydrate_session_from_resume(ctx, resume: bool) -> None:
    from yigthinker.persistence import TranscriptReader, find_latest_session

    if not resume:
        ctx.transcript_path = str(_default_transcript_path())
        return

    sessions_dir = Path.home() / ".yigthinker" / "sessions"
    latest = find_latest_session(sessions_dir)
    if latest:
        ctx.transcript_path = str(latest)
        ctx.messages = TranscriptReader(latest).to_messages()
        console.print(f"Resuming session: {latest.name}")
    else:
        ctx.transcript_path = str(_default_transcript_path())
        console.print("[yellow]No previous session found. Starting fresh.[/]")


def _build(settings: dict):
    from yigthinker.agent import AgentLoop
    from yigthinker.cli.ask_prompt import ask_user_permission
    from yigthinker.hooks.executor import HookExecutor
    from yigthinker.hooks.registry import HookRegistry
    from yigthinker.mcp.loader import MCPLoader
    from yigthinker.permissions import PermissionSystem
    from yigthinker.providers.factory import provider_from_settings
    from yigthinker.registry_factory import build_tool_registry
    from yigthinker.tools.sql.connection import ConnectionPool

    pool = ConnectionPool()
    for name, cfg in settings.get("connections", {}).items():
        pool.add_from_config(name, cfg)

    tools = build_tool_registry(pool=pool)
    mcp_config = Path.cwd() / ".mcp.json"
    if mcp_config.exists():
        try:
            asyncio.run(MCPLoader(mcp_json_path=mcp_config, registry=tools).load())
        except ModuleNotFoundError:
            pass

    hooks = HookExecutor(HookRegistry())
    permissions = PermissionSystem(settings.get("permissions", {}))
    provider = provider_from_settings(settings)
    agent = AgentLoop(
        provider=provider,
        tools=tools,
        hooks=hooks,
        permissions=permissions,
        ask_fn=ask_user_permission,
    )
    return agent, pool


def _run_query(query: str, settings: dict, session) -> str:
    loop, _pool = _build(settings)
    return asyncio.run(loop.run(query, session))


@app.command()
def main(
    query: Optional[str] = typer.Argument(default=None, help="Query (omit for REPL mode)"),
    resume: bool = typer.Option(False, "--resume", help="Resume last session"),
) -> None:
    from yigthinker.cli.repl import Repl
    from yigthinker.plugins.loader import PluginLoader
    from yigthinker.session import SessionContext
    from yigthinker.settings import load_settings

    settings = load_settings()
    ctx = SessionContext(settings=settings)
    _hydrate_session_from_resume(ctx, resume)

    plugin_commands = {
        f"/{command.name}": command.body
        for command in PluginLoader().load_commands()
    }

    if query:
        result = _run_query(query, settings, ctx)
        console.print(result)
        return

    agent, pool = _build(settings)
    repl = Repl(agent_loop=agent, ctx=ctx, pool=pool, plugin_commands=plugin_commands)
    asyncio.run(repl.run_interactive())


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", help="Dashboard host"),
    port: int = typer.Option(8765, help="Dashboard port"),
) -> None:
    """Launch the Yigthinker Web Dashboard."""
    import uvicorn

    from yigthinker.dashboard.layout import create_dash_app
    from yigthinker.dashboard.server import create_app as create_api

    api = create_api()
    create_dash_app()

    console.print(f"[bold blue]Yigthinker Dashboard[/] starting at http://{host}:{port}/dashboard/")
    uvicorn.run(api, host=host, port=port)


if __name__ == "__main__":
    app()
