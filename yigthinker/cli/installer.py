from __future__ import annotations

import locale
import os
import platform
import shutil
import subprocess
import sys

from rich.console import Console
from rich.panel import Panel
from yigthinker.install_hints import (
    DEFAULT_INSTALL_SOURCE,
    INSTALL_SOURCE_ENV,
    build_install_requirement,
    build_uv_tool_install_hint,
    get_install_source,
)

console = Console()


def detect_language() -> str:
    """Return 'zh' or 'en' based on system locale."""
    # 1. Explicit env var override
    for var in ("LANG", "LC_ALL", "LC_MESSAGES"):
        val = os.environ.get(var, "")
        if val.startswith("zh"):
            return "zh"
        if val.startswith("en"):
            return "en"
    # 2. locale.getlocale()
    try:
        loc = locale.getlocale()[0] or ""
        if loc.startswith("zh") or loc.startswith("Chinese"):
            return "zh"
    except ValueError:
        pass
    # 3. Windows fallback: Win32 API
    if platform.system() == "Windows":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            if lang_id in (0x0804, 0x0404):  # zh_CN, zh_TW
                return "zh"
        except (AttributeError, OSError):
            pass
    return "en"


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Yigthinker Installer",
        "subtitle": "AI-powered financial analysis agent",
        "step1_title": "Step 1/2 — Select usage mode",
        "local": "Local Analysis",
        "local_rec": "(recommended)",
        "local_desc": "SQL + DataFrame + Charts + Forecasting",
        "team": "Team Server",
        "team_desc": "All above + Gateway + TUI client",
        "full": "Full Install",
        "full_desc": "All features",
        "prompt_mode": "Select [1/2/3] (default 1)",
        "step2_title": "Step 2/2 — Messaging platforms (optional, Enter to skip)",
        "feishu": "Feishu / Lark",
        "teams": "Microsoft Teams",
        "gchat": "Google Chat",
        "prompt_platforms": "Enter numbers separated by commas, or press Enter to skip",
        "installing": "Installing yigthinker",
        "done": "Installed! Run [bold cyan]yigthinker setup[/] to configure API keys, or [bold cyan]yigthinker quickstart[/] for the guided first run.",
        "already_installed": "Yigthinker is already installed. Reconfigure components?",
        "yes_no": "[Y/n]",
        "abort": "Installation cancelled.",
        "uv_missing": "Error: uv is not available. Install it first: https://docs.astral.sh/uv/",
        "install_failed": "Installation failed.",
        "manual_install": "Manual fallback:",
    },
    "zh": {
        "title": "Yigthinker 安装向导",
        "subtitle": "AI 驱动的财务数据分析助手",
        "step1_title": "第 1/2 步 — 选择使用模式",
        "local": "本地分析",
        "local_rec": "(推荐)",
        "local_desc": "SQL查询 + DataFrame + 图表 + 预测",
        "team": "团队服务",
        "team_desc": "以上全部 + Gateway服务 + TUI客户端",
        "full": "全部安装",
        "full_desc": "所有功能",
        "prompt_mode": "请选择 [1/2/3] (默认 1)",
        "step2_title": "第 2/2 步 — 通讯平台集成 (可选，回车跳过)",
        "feishu": "飞书 / Lark",
        "teams": "Microsoft Teams",
        "gchat": "Google Chat",
        "prompt_platforms": "输入编号，用逗号分隔，或直接回车跳过",
        "installing": "正在安装 yigthinker",
        "done": "安装完成！运行 [bold cyan]yigthinker setup[/] 配置 API Key，或运行 [bold cyan]yigthinker quickstart[/] 进入引导式首跑。",
        "already_installed": "Yigthinker 已安装。是否重新配置组件？",
        "yes_no": "[Y/n]",
        "abort": "安装已取消。",
        "uv_missing": "错误：未找到 uv。请先安装：https://docs.astral.sh/uv/",
        "install_failed": "安装失败。",
        "manual_install": "可手动执行：",
    },
}

_PRESETS: dict[str, list[str]] = {
    "local": ["forecast"],
    "team": ["forecast", "gateway", "tui"],
    "full": ["forecast", "gateway", "tui", "feishu", "teams", "gchat"],
}


def build_extras(mode: str, platforms: list[str]) -> str:
    """Assemble pip extras string from preset mode + selected platforms."""
    parts = list(_PRESETS[mode])
    for p in platforms:
        if p not in parts:
            parts.append(p)
    return ",".join(parts)


def build_manual_install_command(extras: str, source: str | None = None) -> str:
    """Return a copy-pasteable `uv` command for manual fallback installs."""
    return build_uv_tool_install_hint(extras, source=source)


def _is_yigthinker_installed() -> bool:
    """Check if yigthinker is already installed as a uv tool."""
    result = subprocess.run(
        ["uv", "tool", "list"],
        capture_output=True, text=True,
    )
    return "yigthinker" in result.stdout


def _pick_mode(s: dict[str, str]) -> str:
    """Ask user to pick a usage mode. Returns 'local', 'team', or 'full'."""
    console.print(f"\n[bold]{s['step1_title']}[/]\n")
    console.print(f"  [bold cyan]>[/] [bold]1[/]  {s['local']}  [bold green]{s['local_rec']}[/]")
    console.print(f"      [dim]{s['local_desc']}[/]")
    console.print(f"    [bold]2[/]  {s['team']}")
    console.print(f"      [dim]{s['team_desc']}[/]")
    console.print(f"    [bold]3[/]  {s['full']}")
    console.print(f"      [dim]{s['full_desc']}[/]")
    console.print()

    modes = {"1": "local", "2": "team", "3": "full"}
    while True:
        raw = console.input(f"[dim]{s['prompt_mode']}:[/] ").strip()
        if raw == "":
            return "local"
        if raw in modes:
            return modes[raw]
        console.print("[red]Invalid choice.[/]")


def _pick_platforms(s: dict[str, str]) -> list[str]:
    """Ask user to pick messaging platforms. Returns list of extra names."""
    console.print(f"\n[bold]{s['step2_title']}[/]\n")
    console.print(f"    [bold]1[/]  {s['feishu']}")
    console.print(f"    [bold]2[/]  {s['teams']}")
    console.print(f"    [bold]3[/]  {s['gchat']}")
    console.print()

    platform_map = {"1": "feishu", "2": "teams", "3": "gchat"}
    raw = console.input(f"[dim]{s['prompt_platforms']}:[/] ").strip()
    if not raw:
        return []
    selected = []
    for token in raw.replace(" ", "").split(","):
        if token in platform_map and platform_map[token] not in selected:
            selected.append(platform_map[token])
    return selected


def run_install() -> None:
    """Main install wizard entry point."""
    lang = detect_language()
    s = STRINGS[lang]

    # Header
    console.print()
    console.print(Panel.fit(
        f"[bold blue]{s['title']}[/]\n{s['subtitle']}",
        border_style="blue",
    ))

    # Check if uv is available
    if not shutil.which("uv"):
        console.print(f"\n[red]{s['uv_missing']}[/]")
        sys.exit(1)

    # Check if already installed
    if _is_yigthinker_installed():
        console.print(f"\n{s['already_installed']} {s['yes_no']}", end=" ")
        answer = console.input("").strip().lower()
        if answer not in ("", "y", "yes"):
            console.print(f"\n{s['abort']}")
            return

    # Step 1: Usage mode
    mode = _pick_mode(s)

    # Step 2: Messaging platforms (skip if mode is 'full')
    if mode == "full":
        platforms: list[str] = []
    else:
        platforms = _pick_platforms(s)

    # Build extras and install
    extras = build_extras(mode, platforms)
    console.print(f"\n[bold]{s['installing']}[/] [dim]({extras})[/]\n")
    install_requirement = build_install_requirement(extras)

    result = subprocess.run(
        ["uv", "tool", "install", install_requirement],
        capture_output=False,
    )

    if result.returncode != 0:
        console.print(f"\n[red]{s['install_failed']}[/]")
        console.print(f"[dim]{s['manual_install']} {build_manual_install_command(extras)}[/]")
        sys.exit(1)

    console.print(f"\n{s['done']}")
