from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Recommended models per provider
_MODELS = {
    "anthropic": [
        {
            "id": "claude-sonnet-4-5",
            "label": "Claude Sonnet 4.5  [bold green](recommended)[/]",
            "desc": "Best balance of intelligence and speed. Ideal for financial analysis.",
        },
        {
            "id": "claude-opus-4-5",
            "label": "Claude Opus 4.5",
            "desc": "Most capable. Slower and more expensive. Use for complex multi-step tasks.",
        },
        {
            "id": "claude-haiku-4-5",
            "label": "Claude Haiku 4.5",
            "desc": "Fastest and cheapest. Good for quick queries and exploration.",
        },
    ],
    "openai": [
        {
            "id": "gpt-4o",
            "label": "GPT-4o  [bold green](recommended)[/]",
            "desc": "Best OpenAI model for tool use and structured outputs.",
        },
        {
            "id": "gpt-4o-mini",
            "label": "GPT-4o mini",
            "desc": "Faster and cheaper. Good for simple queries.",
        },
    ],
    "ollama": [
        {
            "id": "ollama/llama3.1",
            "label": "Llama 3.1 8B  [bold green](recommended)[/]",
            "desc": "Best free local model for tool use. Requires Ollama running at localhost:11434.",
        },
        {
            "id": "ollama/llama3.1:70b",
            "label": "Llama 3.1 70B",
            "desc": "More capable but needs 40GB+ VRAM.",
        },
    ],
}

_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

_PROVIDER_LABEL = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "ollama": "Ollama (local, free)",
}


def _user_settings_path() -> Path:
    return Path.home() / ".yigthinker" / "settings.json"


def _load_user_settings() -> dict[str, Any]:
    path = _user_settings_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_user_settings(data: dict[str, Any]) -> None:
    path = _user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _pick(prompt: str, options: list[str], default: int = 0) -> int:
    while True:
        for i, opt in enumerate(options):
            marker = "[bold cyan]>[/]" if i == default else " "
            console.print(f"  {marker} [bold]{i + 1}[/]  {opt}")
        raw = console.input(f"\n[dim]Enter number (default {default + 1}):[/] ").strip()
        if raw == "":
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        console.print("[red]Invalid choice, try again.[/]")


def run_setup() -> None:
    console.print(Panel.fit(
        "[bold blue]Yigthinker Setup[/]\n"
        "Configure your LLM provider and API key.\n"
        "Keys are saved to [cyan]~/.yigthinker/settings.json[/] — never in .env files.",
        border_style="blue",
    ))

    # Step 1: Choose provider
    console.print("\n[bold]Step 1 of 3 — Choose your LLM provider[/]\n")
    providers = list(_PROVIDER_LABEL.keys())
    provider_labels = [_PROVIDER_LABEL[p] for p in providers]
    provider_idx = _pick("Provider:", provider_labels, default=0)
    provider = providers[provider_idx]
    console.print(f"\n[green]OK[/] Provider: [bold]{_PROVIDER_LABEL[provider]}[/]\n")

    # Step 2: Choose model
    console.print("[bold]Step 2 of 3 — Choose a model[/]\n")
    models = _MODELS[provider]
    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, m in enumerate(models):
        table.add_row(f"[bold]{i + 1}[/]", m["label"], f"[dim]{m['desc']}[/]")
    console.print(table)
    model_idx = _pick("Model:", [m["label"] for m in models], default=0)
    chosen_model = models[model_idx]["id"]
    console.print(f"\n[green]OK[/] Model: [bold]{chosen_model}[/]\n")

    # Step 3: API key (skip for Ollama)
    api_key: str | None = None
    env_var = _PROVIDER_KEY_ENV.get(provider)

    if env_var:
        console.print(f"[bold]Step 3 of 3 — Enter your API key[/]\n")
        existing = os.environ.get(env_var, "")
        if existing:
            console.print(f"[dim]Found {env_var} in environment ({existing[:8]}...).[/]")
            use_existing = console.input("Use this key? [Y/n]: ").strip().lower()
            if use_existing in ("", "y", "yes"):
                api_key = existing
        if not api_key:
            console.print(f"[dim]Get your key at: {'https://console.anthropic.com' if provider == 'anthropic' else 'https://platform.openai.com/api-keys'}[/]")
            raw = console.input(f"Paste your {env_var}: ").strip()
            if not raw:
                console.print("[red]No key entered. Setup aborted.[/]")
                return
            api_key = raw
    else:
        console.print("[bold]Step 3 of 3 — Ollama setup[/]\n")
        console.print("[dim]Ollama runs locally. Make sure it's running:[/]")
        console.print("  [cyan]ollama serve[/]")
        console.print("  [cyan]ollama pull llama3.1[/]\n")
        console.input("Press Enter when Ollama is ready...")

    # Save settings
    settings = _load_user_settings()
    settings["model"] = chosen_model
    if api_key and env_var:
        settings[env_var.lower()] = api_key  # stored under lowercase key name

    # Also write the key to os.environ so current process can use it immediately
    if api_key and env_var:
        os.environ[env_var] = api_key

    _save_user_settings(settings)

    console.print(Panel.fit(
        f"[bold green]OK Setup complete![/]\n\n"
        f"Provider : [bold]{_PROVIDER_LABEL[provider]}[/]\n"
        f"Model    : [bold]{chosen_model}[/]\n"
        f"Config   : [cyan]~/.yigthinker/settings.json[/]",
        border_style="green",
    ))
    console.print("\nRun [bold cyan]yigthinker[/] to start.\n")
