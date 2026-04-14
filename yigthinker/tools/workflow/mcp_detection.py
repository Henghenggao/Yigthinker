"""MCP package detection for auto-mode deploy.

Per D-02: Yigthinker NEVER calls MCP tools directly from workflow_deploy.
Auto mode only INSPECTS whether the expected MCP package is importable,
then returns instructional next_steps that tell the LLM caller which tool
to invoke on the MCP side.

Detection uses ``importlib.util.find_spec`` which does NOT import the
module - cheap and side-effect-free. This preserves the architect-not-
executor invariant from Phase 9 CONTEXT.
"""
from __future__ import annotations

import importlib.util

from yigthinker.install_hints import build_uv_tool_install_hint

# Target -> MCP package name mapping (Phase 9 Research Pattern 4).
MCP_PACKAGE_MAP: dict[str, str] = {
    "power_automate": "yigthinker_mcp_powerautomate",
    "uipath": "yigthinker_mcp_uipath",
}

# Target -> suggested MCP tool + install hint.
MCP_TOOL_MAP: dict[str, dict[str, str]] = {
    "power_automate": {
        "suggested_tool": "pa_deploy_flow",
        "install_hint": build_uv_tool_install_hint("rpa-pa"),
    },
    "uipath": {
        "suggested_tool": "ui_deploy_process",
        "install_hint": build_uv_tool_install_hint("rpa-uipath"),
    },
}


def check_mcp_installed(package_name: str) -> bool:
    """Return True if the named MCP package is importable.

    Uses ``importlib.util.find_spec`` which only inspects the loader and
    does NOT execute the module's top-level code. Safe to call during
    tool execution.
    """
    try:
        return importlib.util.find_spec(package_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False
