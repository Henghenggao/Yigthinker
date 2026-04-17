#!/usr/bin/env python
"""Import-graph lint: presence/ code must not import yigthinker internals.

Usage:
  python scripts/check_presence_boundaries.py
  python scripts/check_presence_boundaries.py --root <dir>

Exit codes:
  0 = clean
  1 = usage error (e.g. --root path does not exist)
  2 = violations found (prints file:line:message list)
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Known limitations (intentional; documented so future maintainers don't
# assume the lint is airtight):
# - Dynamic imports (importlib.import_module, __import__) are NOT detected.
#   The AST walker only sees static import statements.
# - Deep relative imports (e.g. `from ...agent import X` from inside
#   yigthinker/presence/a/b/) resolve at runtime to `yigthinker.agent` but
#   have node.module == "agent", not the fully-qualified path — so they
#   are not flagged. In practice presence has no such relative imports.
# - Non-UTF-8 files will raise UnicodeDecodeError and abort the lint; all
#   Python source in this repo is UTF-8, so this has never surfaced.

FORBIDDEN_PREFIXES = (
    "yigthinker.agent",
    "yigthinker.session",
    "yigthinker.tools",
    "yigthinker.hooks",
    "yigthinker.permissions",
    "yigthinker.memory",
    "yigthinker.providers",
    "yigthinker.builder",
    "yigthinker.prompts",
)

# TODO(presence-bleed): filepaths relative to repo root that are allowed to break the rule.
# Each entry must have a comment explaining why. Phase 1b budget: <=3 entries.
ALLOWLIST: list[str] = [
    # (populated during migration if genuinely needed)
]


def _is_forbidden(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in FORBIDDEN_PREFIXES)


def _check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (lineno, forbidden_module) for violations in this file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if _is_forbidden(node.module):
                violations.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    violations.append((node.lineno, alias.name))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=None,
        help="Directory to scan (default: yigthinker/presence under the script's repo root).",
    )
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).resolve()
        rel_base = root
    else:
        repo_root = Path(__file__).resolve().parents[1]
        root = repo_root / "yigthinker" / "presence"
        rel_base = repo_root
    if not root.exists():
        print(f"{root} does not exist", file=sys.stderr)
        return 1

    all_violations: list[str] = []
    for py in root.rglob("*.py"):
        try:
            rel = py.relative_to(rel_base)
            rel_str = str(rel).replace("\\", "/")
        except ValueError:
            rel_str = str(py)
        if rel_str in ALLOWLIST:
            continue
        for lineno, mod in _check_file(py):
            all_violations.append(f"{rel_str}:{lineno}: imports forbidden module {mod!r}")

    if all_violations:
        print("Presence boundary violations:", file=sys.stderr)
        for v in all_violations:
            print("  " + v, file=sys.stderr)
        print(
            f"\nTotal: {len(all_violations)} violation(s). "
            "Fix or add to ALLOWLIST with justification.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
