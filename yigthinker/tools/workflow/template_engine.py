"""Jinja2 template engine for workflow script generation.

Wraps SandboxedEnvironment with AST-based post-render validation
and credential pattern scanning. Templates use an inheritance chain:
base/main.py.j2 defines blocks, child templates (power_automate,
uipath) extend via {% extends %}.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# AST validation constants
_BLOCKED_CALLS = {
    "exec", "eval", "__import__", "compile",
    "getattr", "setattr", "delattr",
}
_BLOCKED_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "http",
}
_ALLOWED_IMPORTS = {
    "pandas", "numpy", "sqlalchemy", "yaml", "pyyaml", "json",
    "logging", "pathlib", "datetime", "typing", "requests",
    "openpyxl", "reportlab", "plotly", "checkpoint_utils",
    "collections", "re", "math", "decimal", "csv", "io",
    "dataclasses", "functools", "time",
}

# Dependency mapping from step actions to pip packages
_ACTION_TO_DEPS: dict[str, list[str]] = {
    "sql_query": ["sqlalchemy>=2.0.0", "aiosqlite>=0.20.0"],
    "df_load": ["pandas>=2.0.0", "openpyxl>=3.1.0"],
    "df_transform": ["pandas>=2.0.0"],
    "df_merge": ["pandas>=2.0.0"],
    "chart_create": ["plotly>=5.22.0"],
    "report_generate": ["reportlab>=4.0.0"],
    "finance_calculate": ["numpy>=1.24.0"],
    "finance_analyze": ["numpy>=1.24.0"],
    "finance_validate": ["numpy>=1.24.0"],
    "finance_budget": ["numpy>=1.24.0"],
}

# Credential patterns that should never appear in config output
_CREDENTIAL_PATTERNS = [
    # Connection strings with embedded credentials: ://user:pass@host
    re.compile(r"://[^v\s][^a\s][^\s]*:[^\s]*@"),
    # OpenAI / Stripe-style API keys
    re.compile(r"\bsk-[a-zA-Z0-9]{10,}"),
]


class TemplateEngine:
    """Secure Jinja2 template engine for workflow script generation."""

    def __init__(self) -> None:
        self._env = SandboxedEnvironment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, target: str, context: dict) -> str:
        """Render a main.py script for the given target platform.

        Args:
            target: One of 'python', 'power_automate', 'uipath'.
            context: Template variables (workflow_name, version, steps, etc.).

        Returns:
            Rendered Python script as string.

        Raises:
            ValueError: If AST validation finds dangerous patterns.
        """
        if target == "python":
            template_path = "base/main.py.j2"
        else:
            template_path = f"{target}/main.py.j2"

        template = self._env.get_template(template_path)
        rendered = template.render(**context)

        issues = _validate_rendered_script(rendered)
        if issues:
            raise ValueError(
                f"Rendered script failed AST validation: {issues}"
            )

        return rendered

    def render_checkpoint_utils(self, context: dict) -> str:
        """Render checkpoint_utils.py with workflow-specific variables.

        Args:
            context: Must include workflow_name, checkpoint_ids,
                     max_retries, gateway_url.

        Returns:
            Rendered checkpoint_utils.py as string.
        """
        template = self._env.get_template("base/checkpoint_utils.py.j2")
        return template.render(**context)

    def render_config(self, context: dict) -> str:
        """Render config.yaml with vault:// credential placeholders.

        Args:
            context: Must include workflow_name, version, connections.

        Returns:
            Rendered config.yaml as string.

        Raises:
            ValueError: If credential patterns detected in output.
        """
        template = self._env.get_template("base/config.yaml.j2")
        rendered = template.render(**context)

        issues = _scan_credential_patterns(rendered)
        if issues:
            raise ValueError(
                f"Config contains credential patterns: {issues}"
            )

        return rendered

    def render_requirements(self, context: dict) -> str:
        """Render requirements.txt listing pip dependencies.

        Args:
            context: Must include workflow_name and dependencies list.

        Returns:
            Rendered requirements.txt as string.
        """
        template = self._env.get_template("base/requirements.txt.j2")
        return template.render(**context)

    @staticmethod
    def compute_dependencies(steps: list[dict]) -> list[str]:
        """Map step actions to pip package dependencies.

        Args:
            steps: List of step dicts, each with an 'action' key.

        Returns:
            Sorted, deduplicated list of pip package specifiers.
        """
        deps: set[str] = set()
        for step in steps:
            action = step.get("action", "")
            if action in _ACTION_TO_DEPS:
                deps.update(_ACTION_TO_DEPS[action])
        return sorted(deps)


def _validate_rendered_script(code: str) -> list[str]:
    """AST-check rendered script for dangerous patterns.

    Parses the rendered Python code and walks the AST to detect:
    - Imports of blocked modules (os, sys, subprocess, etc.)
    - Calls to blocked functions (exec, eval, __import__, etc.)

    Returns list of issue strings (empty if clean).
    """
    issues: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Rendered script has syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module in _BLOCKED_MODULES:
                    issues.append(f"Blocked import: {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_module = node.module.split(".")[0]
            if top_module in _BLOCKED_MODULES:
                issues.append(f"Blocked import: {node.module}")
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in _BLOCKED_CALLS
            ):
                issues.append(f"Blocked call: {node.func.id}()")

    return issues


def _scan_credential_patterns(text: str) -> list[str]:
    """Scan rendered config text for credential-like patterns.

    Checks for connection strings with embedded passwords,
    API key prefixes, and other sensitive patterns.

    Returns list of issue strings (empty if clean).
    """
    issues: list[str] = []

    for pattern in _CREDENTIAL_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            issues.append(
                f"Credential pattern detected: {pattern.pattern}"
            )

    return issues
