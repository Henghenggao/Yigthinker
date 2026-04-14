from __future__ import annotations

from yigthinker.install_hints import build_uv_tool_install_hint


TEXTUAL_IMPORT_ERROR = (
    "TUI requires the 'textual' package. Install with: "
    f"{build_uv_tool_install_hint('tui')}"
)
