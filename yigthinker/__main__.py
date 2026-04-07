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
    host: str = typer.Option("127.0.0.1", help="Gateway host"),
    port: int = typer.Option(8766, help="Gateway port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
) -> None:
    """Launch the Yigthinker Web Dashboard (starts Gateway + opens browser)."""
    import uvicorn

    from yigthinker.dashboard.sample_db import ensure_sample_db
    from yigthinker.gateway.server import GatewayServer
    from yigthinker.settings import load_settings

    settings = load_settings()
    gw_cfg = settings.get("gateway", {})
    resolved_host = gw_cfg.get("host") or host
    resolved_port = gw_cfg.get("port") or port

    # Ensure sample DB exists for first-time experience
    sample_path = ensure_sample_db()
    console.print(f"[dim]Sample database: {sample_path}[/]")

    gateway = GatewayServer(settings)
    url = f"http://{resolved_host}:{resolved_port}/dashboard/"
    console.print(f"[bold blue]Yigthinker Dashboard[/] starting at {url}")

    if not no_browser:
        import threading
        import time
        import webbrowser

        def _open_browser():
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(gateway.app, host=resolved_host, port=resolved_port)


@app.command()
def quickstart(
    port: int = typer.Option(8766, help="Port for the gateway + dashboard"),
) -> None:
    """First-time setup: configure API key, create sample data, launch dashboard."""
    import os

    from rich.panel import Panel

    from yigthinker.settings import load_settings, has_api_key

    console.print(Panel.fit(
        "[bold blue]Yigthinker Quick Start[/]\n"
        "Set up your AI data analyst in 3 steps.",
        border_style="blue",
    ))

    # Step 1: Check if setup is needed
    settings = load_settings()
    need_setup = not has_api_key(settings)

    if need_setup:
        console.print("\n[bold]Step 1/3[/] — Configure your LLM provider\n")
        from yigthinker.cli.setup_wizard import run_setup
        run_setup()
        # Reload settings after setup
        settings = load_settings()
        if not has_api_key(settings):
            console.print("[red]Setup incomplete. Run [bold]yigthinker quickstart[/] again.[/]")
            return
    else:
        model = settings.get("model", "unknown")
        console.print(f"\n[bold]Step 1/3[/] — LLM provider [green]already configured[/] (model: [bold]{model}[/])")

    # Step 2: Create sample database
    console.print(f"\n[bold]Step 2/3[/] — Creating sample finance database")
    from yigthinker.dashboard.sample_db import ensure_sample_db
    sample_path = ensure_sample_db()
    console.print(f"  [green]OK[/] Sample data at [cyan]{sample_path}[/]")
    console.print("  [dim]3 tables: revenue (18 rows), accounts_payable (18 rows), expenses (300 rows)[/]")

    # Step 3: Show token and start dashboard
    console.print(f"\n[bold]Step 3/3[/] — Starting dashboard\n")

    from yigthinker.gateway.auth import GatewayAuth
    auth = GatewayAuth()
    token = auth.token

    console.print(Panel.fit(
        f"[bold green]Your gateway token[/] (paste this into the dashboard):\n\n"
        f"  [bold cyan]{token}[/]\n\n"
        f"[dim]Token saved at: ~/.yigthinker/gateway.token\n"
        f"The dashboard will remember it after first login.[/]",
        border_style="green",
    ))

    import uvicorn

    from yigthinker.gateway.server import GatewayServer

    gateway = GatewayServer(settings)
    url = f"http://127.0.0.1:{port}/dashboard/"
    console.print(f"[bold blue]Dashboard[/] → [bold]{url}[/]")
    console.print("[dim]Press Ctrl+C to stop.\n[/]")

    import threading
    import time
    import webbrowser

    def _open_browser():
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(gateway.app, host="127.0.0.1", port=port)


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
