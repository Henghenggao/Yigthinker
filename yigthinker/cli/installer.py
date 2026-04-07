from __future__ import annotations

import locale
import os
import platform


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
        "done": "Installed! Run [bold cyan]yigthinker setup[/] to configure API keys and data sources.",
        "already_installed": "Yigthinker is already installed. Reconfigure components?",
        "yes_no": "[Y/n]",
        "abort": "Installation cancelled.",
        "uv_missing": "Error: uv is not available. Install it first: https://docs.astral.sh/uv/",
        "install_failed": "Installation failed. Try manually: uv tool install yigthinker",
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
        "done": "安装完成！运行 [bold cyan]yigthinker setup[/] 配置 API Key 和数据源。",
        "already_installed": "Yigthinker 已安装。是否重新配置组件？",
        "yes_no": "[Y/n]",
        "abort": "安装已取消。",
        "uv_missing": "错误：未找到 uv。请先安装：https://docs.astral.sh/uv/",
        "install_failed": "安装失败。请尝试手动安装：uv tool install yigthinker",
    },
}

_PRESETS: dict[str, list[str]] = {
    "local": ["forecast", "dashboard"],
    "team": ["forecast", "dashboard", "gateway", "tui"],
    "full": ["forecast", "dashboard", "gateway", "tui", "feishu", "teams", "gchat"],
}


def build_extras(mode: str, platforms: list[str]) -> str:
    """Assemble pip extras string from preset mode + selected platforms."""
    parts = list(_PRESETS[mode])
    for p in platforms:
        if p not in parts:
            parts.append(p)
    return ",".join(parts)
