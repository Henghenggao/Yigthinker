from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import sys
from typing import Optional
import uuid

import typer
from rich.console import Console
from typer.main import get_command

app = typer.Typer(help="Yigthinker - AI-powered financial analysis agent")
console = Console()
_ROOT_COMMANDS = frozenset({"install", "setup", "main", "quickstart", "gateway", "tui"})
_ROOT_HELP_FLAGS = frozenset({"--help", "--install-completion", "--show-completion"})


@app.command("install")
def install_command() -> None:
    """Interactive installer — configure usage mode and components."""
    from yigthinker.cli.installer import run_install

    run_install()


@app.command("setup")
def setup_command() -> None:
    """Configure your LLM provider and API key without launching the gateway."""
    from yigthinker.cli.setup_wizard import run_setup

    run_setup()


def _default_transcript_path() -> Path:
    sessions_dir = Path.home() / ".yigthinker" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return sessions_dir / f"session-{timestamp}-{uuid.uuid4().hex[:8]}.jsonl"


def _normalize_cli_args(argv: list[str]) -> list[str]:
    """Route bare invocations to the documented default `main` command."""
    if not argv:
        return ["main"]

    first = argv[0]
    if first in _ROOT_COMMANDS or first in _ROOT_HELP_FLAGS:
        return argv

    if first.startswith("-"):
        return ["main", *argv]

    return ["main", *argv]


def _client_url_host(host: str) -> str:
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


def _resolve_gateway_binding(
    settings: dict,
    host: str | None,
    port: int | None,
) -> tuple[str, int]:
    gw_cfg = settings.setdefault("gateway", {})
    resolved_host = host or gw_cfg.get("host") or "127.0.0.1"
    resolved_port = port or gw_cfg.get("port") or 8766
    gw_cfg["host"] = resolved_host
    gw_cfg["port"] = resolved_port
    return resolved_host, resolved_port


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
    """Start interactive REPL or run a single-shot query."""
    from yigthinker.settings import load_settings, has_api_key

    settings = load_settings()
    if not has_api_key(settings):
        model = settings.get("model", "unknown")
        console.print(
            f"[red]No API key found for model [bold]{model}[/bold].[/]\n"
            "Run [bold]yigthinker quickstart[/] to configure your provider,\n"
            "or set the appropriate environment variable:\n"
            "  [dim]ANTHROPIC_API_KEY[/]   for Claude models\n"
            "  [dim]OPENAI_API_KEY[/]      for OpenAI models\n"
            "  [dim]AZURE_OPENAI_API_KEY[/] for Azure deployments\n"
            "  Ollama models need no key (uses local endpoint)."
        )
        raise typer.Exit(code=1)
    asyncio.run(_async_main(query, resume, settings))


@app.command()
def quickstart(
    port: int = typer.Option(8766, help="Port for the gateway"),
) -> None:
    """First-time setup: configure API key, create sample data, launch gateway."""

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

    # Step 2: Create sample database and wire it as a connection
    console.print("\n[bold]Step 2/3[/] — Creating sample finance database")
    from yigthinker.sample_db import ensure_sample_db
    sample_path = ensure_sample_db()
    # Register sample DB as a named connection so sql_query can reach it
    connections = settings.setdefault("connections", {})
    if "sample" not in connections:
        connections["sample"] = {"type": "sqlite", "database": str(sample_path)}
    console.print(f"  [green]OK[/] Sample data at [cyan]{sample_path}[/]")
    console.print("  [dim]3 tables: revenue (18 rows), accounts_payable (18 rows), expenses (300 rows)[/]")
    console.print("  [dim]Connection registered as [bold]sample[/] — use /connect sample[/]")

    # Step 3: Launch gateway
    console.print("\n[bold]Step 3/3[/] — Starting gateway\n")

    from yigthinker.gateway.auth import GatewayAuth
    auth = GatewayAuth()
    token = auth.token

    console.print(Panel.fit(
        f"[bold green]Your gateway token[/]:\n\n"
        f"  [bold cyan]{token}[/]\n\n"
        f"[dim]Token saved at: ~/.yigthinker/gateway.token\n"
        f"Use this token to connect from TUI or IM channels.[/]",
        border_style="green",
    ))

    import uvicorn

    from yigthinker.gateway.server import GatewayServer

    gateway = GatewayServer(settings)
    url = f"http://127.0.0.1:{port}"
    console.print(f"[bold blue]Gateway[/] → [bold]{url}/health[/]")
    console.print("[dim]Press Ctrl+C to stop.\n[/]")

    uvicorn.run(gateway.app, host="127.0.0.1", port=port)


@app.command("gateway")
def gateway_start(
    host: str | None = typer.Option(None, help="Gateway host (default: from settings or 127.0.0.1)"),
    port: int | None = typer.Option(None, help="Gateway port (default: from settings or 8766)"),
) -> None:
    """Start the Yigthinker Gateway (foreground)."""
    import logging
    import uvicorn

    from yigthinker.gateway.server import GatewayServer
    from yigthinker.settings import load_settings

    # quick-260416-j3y: surface tool_call / tool_result diagnostic logs from
    # yigthinker.agent when running the gateway. Without this, uvicorn only
    # ships its own loggers' records and the agent's INFO logs stay silent.
    logging.getLogger("yigthinker").setLevel(logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    settings = load_settings()
    resolved_host, resolved_port = _resolve_gateway_binding(settings, host, port)
    client_host = _client_url_host(resolved_host)

    gateway = GatewayServer(settings)
    console.print(f"[bold blue]Yigthinker Gateway[/] starting at http://{client_host}:{resolved_port}")
    console.print(f"Health check: http://{client_host}:{resolved_port}/health")
    uvicorn.run(gateway.app, host=resolved_host, port=resolved_port)


@app.command("tui")
def tui_command(
    host: str | None = typer.Option(None, help="Gateway host (default: from settings or 127.0.0.1)"),
    port: int | None = typer.Option(None, help="Gateway port (default: from settings or 8766)"),
) -> None:
    """Launch the Yigthinker TUI client."""
    from yigthinker.settings import load_settings

    settings = load_settings()
    resolved_host, resolved_port = _resolve_gateway_binding(settings, host, port)

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


def run(argv: list[str] | None = None) -> None:
    args = _normalize_cli_args(list(sys.argv[1:] if argv is None else argv))
    get_command(app).main(args=args, prog_name="yigthinker")


if __name__ == "__main__":
    run()
