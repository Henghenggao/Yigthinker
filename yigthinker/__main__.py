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


async def _async_main(
    query: str | None,
    resume: bool,
    settings: dict,
) -> None:
    from yigthinker.builder import build_app
    from yigthinker.cli.repl import Repl
    from yigthinker.plugins.loader import PluginLoader
    from yigthinker.session import SessionContext

    ctx = SessionContext(settings=settings)
    _hydrate_session_from_resume(ctx, resume)

    plugin_commands = {
        f"/{command.name}": command.body
        for command in PluginLoader().load_commands()
    }

    app_ctx = await build_app(settings)

    if query:
        result = await app_ctx.agent_loop.run(query, ctx)
        console.print(result)
        return

    repl = Repl(
        agent_loop=app_ctx.agent_loop,
        ctx=ctx,
        pool=app_ctx.pool,
        plugin_commands=plugin_commands,
    )
    await repl.run_interactive()


@app.command()
def main(
    query: Optional[str] = typer.Argument(default=None, help="Query (omit for REPL mode)"),
    resume: bool = typer.Option(False, "--resume", help="Resume last session"),
) -> None:
    from yigthinker.settings import load_settings

    settings = load_settings()
    asyncio.run(_async_main(query, resume, settings))


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


@app.command("gateway")
def gateway_start(
    host: str = typer.Option("127.0.0.1", help="Gateway host"),
    port: int = typer.Option(8766, help="Gateway port"),
) -> None:
    """Start the Yigthinker Gateway (foreground)."""
    import uvicorn

    from yigthinker.gateway.server import GatewayServer
    from yigthinker.settings import load_settings

    settings = load_settings()
    gw_cfg = settings.get("gateway", {})
    resolved_host = gw_cfg.get("host") or host
    resolved_port = gw_cfg.get("port") or port

    gateway = GatewayServer(settings)
    console.print(f"[bold blue]Yigthinker Gateway[/] starting at http://{resolved_host}:{resolved_port}")
    console.print(f"Health check: http://{resolved_host}:{resolved_port}/health")
    uvicorn.run(gateway.app, host=resolved_host, port=resolved_port)


@app.command("tui")
def tui_command(
    host: str = typer.Option("", help="Gateway host (default: from settings)"),
    port: int = typer.Option(0, help="Gateway port (default: from settings)"),
) -> None:
    """Launch the Yigthinker TUI client."""
    from yigthinker.settings import load_settings

    settings = load_settings()
    gw_cfg = settings.get("gateway", {})
    resolved_host = host or gw_cfg.get("host", "127.0.0.1")
    resolved_port = port or gw_cfg.get("port", 8766)

    token_path = Path.home() / ".yigthinker" / "gateway.token"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
    else:
        token = ""
        console.print("[yellow]Warning: Gateway token not found. Start gateway first: yigthinker gateway[/]")

    from yigthinker.tui import YigthinkerTUI

    tui = YigthinkerTUI(
        gateway_url=f"ws://{resolved_host}:{resolved_port}/ws",
        token=token,
    )
    tui.run()


if __name__ == "__main__":
    app()
