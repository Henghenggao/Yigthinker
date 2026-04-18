"""PyPI publish helper — validate, build, and emit twine commands.

Handles the three-package Yigthinker release: the core `yigthinker` plus the
two MCP packages under `packages/`. Never uploads anything itself — the
final `twine upload` step is always explicit and user-driven so PyPI tokens
stay out of this script's runtime.

Usage
-----
    python scripts/pypi_publish_helper.py check
        Validate pyproject.toml metadata (version, authors, urls, license,
        classifiers) for all three packages. Non-zero exit on violations.

    python scripts/pypi_publish_helper.py build [--version X.Y.Za1]
        Run `python -m build` for each package. If --version is given,
        rewrites the `version = "..."` line in each pyproject.toml first
        and confirms with the user before proceeding. Without --version,
        builds whatever the files currently declare.

    python scripts/pypi_publish_helper.py upload-command [--repository pypi|testpypi]
        Emit the exact twine upload commands (one per package) to stdout.
        User copies + runs them; this script never has your PyPI token.

Design notes
------------
- Dependencies on `build` / `twine` are runtime-only, not imported here.
  The script just calls them as subprocess + prints install hints.
- All three packages build in-place via hatchling — no monorepo orchestrator.
- We do NOT touch `sys.path` or import any package under test; this keeps
  the script safe to run in a minimal venv.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# (display_name, path_to_pyproject_dir, pypi_canonical_name)
PACKAGES: tuple[tuple[str, Path, str], ...] = (
    ("core", REPO_ROOT, "yigthinker"),
    ("uipath-mcp", REPO_ROOT / "packages" / "yigthinker-mcp-uipath", "yigthinker-mcp-uipath"),
    ("pa-mcp", REPO_ROOT / "packages" / "yigthinker-mcp-powerautomate", "yigthinker-mcp-powerautomate"),
)

# PyPI metadata fields that are *strongly recommended* for a real release.
# `name` and `version` are already enforced by pyproject.toml parsers so we
# skip them. License + authors + urls are the ones PyPI maintainers flag.
RECOMMENDED_FIELDS = ("authors", "license", "classifiers")
RECOMMENDED_URL_KEYS = ("Homepage", "Repository")


@dataclass(frozen=True)
class Violation:
    package: str
    field: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.package}] {self.field}: {self.detail}"


# ---------------------------------------------------------------------------
# Metadata validation
# ---------------------------------------------------------------------------

def _read_pyproject(path: Path) -> str:
    return (path / "pyproject.toml").read_text(encoding="utf-8")


def _extract_table_value(text: str, key: str) -> str | None:
    """Tolerant extractor — reads the raw string after `key = `.

    Handles both `version = "0.1.0"` (single-line) and multi-line list / dict
    values by capturing until the next top-level key or EOF. We don't use
    tomllib here because the goal is to print line-numbered hints for the
    user, not to parse TOML precisely.
    """
    pat = re.compile(rf"^{re.escape(key)}\s*=\s*(.+?)(?=^\S|\Z)", re.MULTILINE | re.DOTALL)
    m = pat.search(text)
    return m.group(1).strip() if m else None


def validate_metadata() -> list[Violation]:
    violations: list[Violation] = []
    for display, path, canonical in PACKAGES:
        text = _read_pyproject(path)
        # Each field must be present in the [project] table. Simplest check:
        # substring-search for `<field> = ` at line start.
        for field in RECOMMENDED_FIELDS:
            if not re.search(rf"^{re.escape(field)}\s*=", text, re.MULTILINE):
                violations.append(Violation(
                    package=display,
                    field=field,
                    detail=f"missing `{field} = ...` under [project] in {path / 'pyproject.toml'}",
                ))
        # [project.urls] section + at least one of Homepage/Repository
        if not re.search(r"^\[project\.urls\]", text, re.MULTILINE):
            violations.append(Violation(
                package=display,
                field="urls",
                detail=f"missing [project.urls] section in {path / 'pyproject.toml'}",
            ))
        else:
            if not any(re.search(rf"^{re.escape(k)}\s*=", text, re.MULTILINE) for k in RECOMMENDED_URL_KEYS):
                violations.append(Violation(
                    package=display,
                    field="urls",
                    detail=f"[project.urls] present but has neither Homepage nor Repository",
                ))
        # README reference (PyPI long description)
        if not re.search(r"^readme\s*=", text, re.MULTILINE):
            violations.append(Violation(
                package=display,
                field="readme",
                detail="no `readme = \"README.md\"` under [project] — PyPI long description will be blank",
            ))
    return violations


# ---------------------------------------------------------------------------
# Version bump
# ---------------------------------------------------------------------------

def _rewrite_version(path: Path, new_version: str) -> tuple[str, str]:
    """Rewrite the version line in-place. Returns (old_version, new_version)."""
    pyproject = path / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if m is None:
        raise RuntimeError(f"no version line found in {pyproject}")
    old = m.group(1)
    new_text = text[:m.start()] + f'version = "{new_version}"' + text[m.end():]
    pyproject.write_text(new_text, encoding="utf-8")
    return old, new_version


def _confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _ensure_build_installed() -> None:
    if shutil.which("python") is None:
        raise RuntimeError("python not on PATH")
    try:
        subprocess.run(
            [sys.executable, "-c", "import build"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "The `build` package is not installed. Run:\n"
            "  pip install build twine\n"
            "then re-run this helper."
        )


def build_all(rewrite_version: str | None) -> list[Path]:
    _ensure_build_installed()

    if rewrite_version is not None:
        if not re.fullmatch(r"\d+\.\d+\.\d+([ab]\d+|rc\d+)?", rewrite_version):
            raise SystemExit(f"refusing to write non-PEP440 version: {rewrite_version!r}")
        changes = []
        for display, path, _ in PACKAGES:
            old, new = _rewrite_version(path, rewrite_version)
            changes.append((display, path, old, new))
        print("Planned version bumps:")
        for display, path, old, new in changes:
            print(f"  {display}: {old} -> {new}  ({path / 'pyproject.toml'})")
        if not _confirm("Commit these pyproject.toml changes?"):
            # Roll back
            for _, path, old, _ in changes:
                _rewrite_version(path, old)
            raise SystemExit("Version bump aborted. Files restored.")

    artifacts: list[Path] = []
    for display, path, _ in PACKAGES:
        dist_dir = path / "dist"
        # Clean old artifacts so `twine upload dist/*` doesn't accidentally
        # upload a stale file from a previous attempt.
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        print(f"\n=== building {display} @ {path} ===")
        subprocess.run(
            [sys.executable, "-m", "build", "--sdist", "--wheel", str(path)],
            check=True,
        )
        produced = sorted(dist_dir.glob("*"))
        if not produced:
            raise SystemExit(f"build produced no artifacts for {display}")
        artifacts.extend(produced)
        for p in produced:
            print(f"  -> {p.relative_to(REPO_ROOT)}")
    return artifacts


# ---------------------------------------------------------------------------
# Upload command emission (never runs upload itself)
# ---------------------------------------------------------------------------

def emit_upload_commands(repository: str) -> None:
    print(f"\n# Run these manually once you have a {repository} token ready.")
    print(f"# twine will read TWINE_USERNAME=__token__ + TWINE_PASSWORD=<your pypi token>")
    print(f"# (or ~/.pypirc with a [{repository}] section).\n")
    for display, path, canonical in PACKAGES:
        rel = (path / "dist").relative_to(REPO_ROOT)
        # Use --skip-existing so re-running doesn't fail on already-uploaded
        # artifacts — common when retrying after a partial failure.
        print(f"twine upload --repository {repository} --skip-existing "
              f"{rel.as_posix()}/*")
    print(f"\n# After upload, verify with:")
    for _, _, canonical in PACKAGES:
        print(f"  pip install --index-url https://{'test.pypi.org/simple/' if repository == 'testpypi' else 'pypi.org/simple/'} "
              f"{canonical}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="validate metadata + list violations")

    b = sub.add_parser("build", help="run `python -m build` on all 3 packages")
    b.add_argument("--version", default=None,
                   help="if set, rewrite all 3 pyproject.toml to this version first (PEP 440)")

    u = sub.add_parser("upload-command", help="emit twine upload commands")
    u.add_argument("--repository", default="pypi", choices=("pypi", "testpypi"))

    args = p.parse_args(argv)

    if args.cmd == "check":
        vs = validate_metadata()
        if not vs:
            print("OK: all 3 packages have the recommended metadata.")
            return 0
        print(f"FOUND {len(vs)} metadata issue(s):")
        for v in vs:
            print(f"  - {v}")
        print("\nFix these before a real 0.2.0 release.")
        print("Name-reservation 0.1.0a1 can proceed without them (PyPI accepts), "
              "but you'll want them before anyone does `pip install` seriously.")
        return 1

    if args.cmd == "build":
        build_all(rewrite_version=args.version)
        return 0

    if args.cmd == "upload-command":
        emit_upload_commands(args.repository)
        return 0

    return 0  # unreachable


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
