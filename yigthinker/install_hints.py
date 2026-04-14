from __future__ import annotations

DEFAULT_INSTALL_SOURCE = "git+https://github.com/Henghenggao/Yigthinker.git"
INSTALL_SOURCE_ENV = "YIGTHINKER_INSTALL_SOURCE"


def get_install_source(source: str | None = None) -> str:
    """Return the current package source for user-facing install commands."""
    import os

    if source is not None and source.strip():
        return source.strip()
    return (
        os.environ.get(INSTALL_SOURCE_ENV, DEFAULT_INSTALL_SOURCE).strip()
        or DEFAULT_INSTALL_SOURCE
    )


def build_install_requirement(extras: str = "", source: str | None = None) -> str:
    """Return a PEP 508 direct reference for the Yigthinker package."""
    extra_suffix = f"[{extras}]" if extras else ""
    return f"yigthinker{extra_suffix} @ {get_install_source(source)}"


def build_uv_tool_install_hint(extras: str = "", source: str | None = None) -> str:
    """Return a copy-pasteable `uv tool install` command."""
    return f'uv tool install "{build_install_requirement(extras, source=source)}"'
