from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = (
    REPO_ROOT / "packages" / "yigthinker-mcp-uipath",
    REPO_ROOT / "packages" / "yigthinker-mcp-powerautomate",
)


def run(command: list[str], cwd: Path = REPO_ROOT, timeout: int | None = None) -> None:
    rendered = " ".join(command)
    print(f"\n==> ({cwd}) {rendered}", flush=True)
    # ``timeout`` fails loud with a CalledProcessError/TimeoutExpired if a child hangs,
    # instead of letting CI silently wait out the 6-hour default.
    subprocess.run(command, cwd=cwd, check=True, timeout=timeout)


def install_test_dependencies() -> None:
    # Install timeouts are generous because pip resolves + downloads wheels.
    run([sys.executable, "-m", "pip", "install", "-e", ".[test]"], timeout=600)
    run(
        [sys.executable, "-m", "pip", "install", "-e", "packages/yigthinker-mcp-uipath[test]"],
        timeout=600,
    )
    run(
        [sys.executable, "-m", "pip", "install", "-e", "packages/yigthinker-mcp-powerautomate[test]"],
        timeout=600,
    )


def run_test_suites() -> None:
    # Root suite currently runs in ~2-7 min; cap at 15 min.
    run([sys.executable, "-m", "pytest", "-q"], timeout=900)
    # MCP package suites are tiny (~2s each); cap at 5 min to surface any hang.
    for package_dir in PACKAGE_DIRS:
        run([sys.executable, "-m", "pytest", "-q"], cwd=package_dir, timeout=300)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install test dependencies and run the root + MCP package suites.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Assume the current interpreter already has all test dependencies installed.",
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help="Install test dependencies and exit — used by the CI workflow which runs suites separately.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.install_only:
        install_test_dependencies()
        return
    if not args.skip_install:
        install_test_dependencies()
    run_test_suites()


if __name__ == "__main__":
    main()
